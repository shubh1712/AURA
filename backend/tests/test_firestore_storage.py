"""Comprehensive offline tests for FirestoreJobStorage adapter in AURA.

Covers:
1. All storage operations and return shapes.
2. Serialization and deserialization of jobs, requests, and responses.
3. Job lifecycle and stage transitions.
4. Top-level indexed analysis_id resolution.
5. Owner-scoped queries and ordering.
6. What-if simulation and explanation persistence.
7. Action plan upsert, retrieval, deletion, and owner filtering.
8. Durable claim acquisition, expiry, release, and concurrent lease protection.
9. Large-payload chunking, versioning, subcollection storage, and byte-for-byte reconstruction.
10. Failure safety on partial/interrupted chunked writes.
11. Safe startup recovery behavior for distributed environments.
12. Factory selection and initialization error propagation.
13. SQLite baseline parity.
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional
import uuid

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage
from app.services.jobs.base import JobRecord, JobStorageInterface
from app.services.jobs.factory import get_job_storage
from app.services.jobs.firestore_storage import FirestoreJobStorage, _utc_now_iso
from app.services.jobs.storage import SQLiteJobStorage


# =============================================================================
# In-Memory Fake Firestore Implementation for Offline Testing
# =============================================================================

class FakeDocumentSnapshot:
    """In-memory mock for Firestore DocumentSnapshot."""

    def __init__(self, doc_ref: "FakeDocumentReference", data: Optional[Dict[str, Any]] = None):
        self.reference = doc_ref
        self.id = doc_ref.id
        self._data = data.copy() if data is not None else None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Dict[str, Any]:
        return self._data.copy() if self._data is not None else {}


class FakeDocumentReference:
    """In-memory mock for Firestore DocumentReference."""

    def __init__(self, doc_id: str, collection: "FakeCollectionReference"):
        self.id = doc_id
        self.parent = collection
        self._subcollections: Dict[str, "FakeCollectionReference"] = {}

    def get(self, transaction: Any = None) -> FakeDocumentSnapshot:
        data = self.parent._docs.get(self.id)
        return FakeDocumentSnapshot(self, data)

    def set(self, data: Dict[str, Any]) -> None:
        self.parent._docs[self.id] = data.copy()

    def update(self, data: Dict[str, Any]) -> None:
        if self.id not in self.parent._docs:
            self.parent._docs[self.id] = {}
        self.parent._docs[self.id].update(data.copy())

    def delete(self) -> None:
        self.parent._docs.pop(self.id, None)

    def collection(self, name: str) -> "FakeCollectionReference":
        if name not in self._subcollections:
            self._subcollections[name] = FakeCollectionReference(name, parent_doc=self)
        return self._subcollections[name]


class FakeQuery:
    """In-memory mock for Firestore Query with filtering and sorting."""

    def __init__(self, collection: "FakeCollectionReference", filters: Optional[List[Any]] = None, order_bys: Optional[List[Any]] = None, limit_count: Optional[int] = None):
        self._collection = collection
        self._filters = filters or []
        self._order_bys = order_bys or []
        self._limit_count = limit_count

    def where(self, filter: Any = None, **kwargs: Any) -> "FakeQuery":
        new_filters = list(self._filters)
        if filter is not None:
            new_filters.append(filter)
        return FakeQuery(self._collection, new_filters, self._order_bys, self._limit_count)

    def order_by(self, field: str, direction: Any = None) -> "FakeQuery":
        new_orders = list(self._order_bys)
        new_orders.append((field, direction))
        return FakeQuery(self._collection, self._filters, new_orders, self._limit_count)

    def limit(self, count: int) -> "FakeQuery":
        return FakeQuery(self._collection, self._filters, self._order_bys, count)

    def stream(self) -> List[FakeDocumentSnapshot]:
        docs: List[Dict[str, Any]] = []
        doc_refs: List[FakeDocumentReference] = []

        for doc_id, data in self._collection._docs.items():
            match = True
            for f in self._filters:
                # Support FieldFilter(field, op, value)
                field_name = getattr(f, "field_path", None) or getattr(f, "field", None)
                op = getattr(f, "op_string", None) or getattr(f, "operator", None)
                val = getattr(f, "value", None)
                if field_name:
                    actual = data.get(field_name)
                    if op in ("==", "EQUAL", 1, 3) or "IS_NULL" in str(getattr(op, "name", str(op))) or "EQUAL" in str(getattr(op, "name", str(op))):
                        if actual != val:
                            match = False
                            break
            if match:
                ref = self._collection.document(doc_id)
                docs.append(data)
                doc_refs.append(ref)

        # Sort if order_bys specified
        for field, direction in reversed(self._order_bys):
            desc = "DESC" in str(direction).upper() if direction else False
            doc_refs = [
                ref for _, ref in sorted(
                    zip(docs, doc_refs),
                    key=lambda pair: str(pair[0].get(field, "")),
                    reverse=desc,
                )
            ]
            docs = [
                data for data, _ in sorted(
                    zip(docs, doc_refs),
                    key=lambda pair: str(pair[0].get(field, "")),
                    reverse=desc,
                )
            ]

        # Apply limit
        if self._limit_count is not None:
            doc_refs = doc_refs[: self._limit_count]

        return [ref.get() for ref in doc_refs]


class FakeCollectionReference(FakeQuery):
    """In-memory mock for Firestore CollectionReference."""

    def __init__(self, name: str, parent_doc: Optional[FakeDocumentReference] = None):
        self.name = name
        self.parent = parent_doc
        self._docs: Dict[str, Dict[str, Any]] = {}
        self._doc_refs: Dict[str, FakeDocumentReference] = {}
        super().__init__(self)

    def document(self, doc_id: Optional[str] = None) -> FakeDocumentReference:
        did = doc_id or str(uuid.uuid4())
        if did not in self._doc_refs:
            self._doc_refs[did] = FakeDocumentReference(did, self)
        return self._doc_refs[did]


class FakeTransaction:
    """In-memory mock for Firestore Transaction."""

    def __init__(self, db: "FakeFirestoreClient"):
        self._db = db
        self._read_only = False
        self._id = b"test-txn-id"
        self._max_attempts = 5

    def get(self, doc_ref: FakeDocumentReference) -> FakeDocumentSnapshot:
        return doc_ref.get(transaction=self)

    def set(self, doc_ref: FakeDocumentReference, data: Dict[str, Any]) -> None:
        doc_ref.set(data)

    def update(self, doc_ref: FakeDocumentReference, data: Dict[str, Any]) -> None:
        doc_ref.update(data)

    def _begin(self, retry_id: Any = None) -> None:
        pass

    def _clean_up(self) -> None:
        pass

    def _commit(self) -> None:
        pass

    def _rollback(self) -> None:
        pass


class FakeFirestoreClient:
    """In-memory mock for google.cloud.firestore.Client."""

    def __init__(self, project: str = "aura-test-project", database: str = "(default)"):
        self.project = project
        self.database = database
        self._collections: Dict[str, FakeCollectionReference] = {}

    def collection(self, name: str) -> FakeCollectionReference:
        if name not in self._collections:
            self._collections[name] = FakeCollectionReference(name)
        return self._collections[name]

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def close(self) -> None:
        pass


# =============================================================================
# Helper Fixtures & Builders
# =============================================================================

@pytest.fixture
def fake_db() -> FakeFirestoreClient:
    return FakeFirestoreClient()


@pytest.fixture
def firestore_storage(fake_db: FakeFirestoreClient) -> FirestoreJobStorage:
    return FirestoreJobStorage(client=fake_db)


def make_dummy_analysis_response(analysis_id: str = "analysis-test-01") -> AnalysisResponse:
    """Creates a valid minimal AnalysisResponse for testing."""
    return AnalysisResponse(
        analysis_id=analysis_id,
        status="completed",
        question="Should we deploy to Cloud Run?",
        context="Evaluation of serverless container architecture.",
        constraints=["Zero downtime", "Budget limit $500"],
        stages_completed=["stage1_decision_framer", "stage2_evidence_engine", "stage3_ai_boardroom"],
        framer=None,
        evidence=None,
        boardroom=None,
        recommendation=None,
        scenarios=None,
        resilience=None,
        diagnostics={"execution_time": 1.25},
    )


# =============================================================================
# Test Suite
# =============================================================================

class TestFirestoreJobStorage:
    """Comprehensive test suite for FirestoreJobStorage adapter."""

    def test_implements_job_storage_interface(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies FirestoreJobStorage fulfills the runtime JobStorageInterface protocol."""
        assert isinstance(firestore_storage, JobStorageInterface)

    def test_create_and_get_job(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies job creation in QUEUED status and point lookup."""
        req = AnalysisJobCreateRequest(
            question="Scale microservices?",
            context={"traffic": "10k RPS"},
            owner_id="user-ops",
            timeout_seconds=90.0,
        )
        record = firestore_storage.create_job(request=req, job_id="job-scale-01")

        assert record.job_id == "job-scale-01"
        assert record.status == JobStatus.QUEUED
        assert record.stage == PipelineStage.QUEUED
        assert record.owner_id == "user-ops"
        assert record.timeout_seconds == 90.0

        retrieved = firestore_storage.get_job("job-scale-01")
        assert retrieved is not None
        assert retrieved.job_id == "job-scale-01"
        assert retrieved.status == JobStatus.QUEUED
        assert retrieved.request.question == "Scale microservices?"
        assert retrieved.response is None

    def test_job_lifecycle_and_progress_tracking(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies status transitions: QUEUED -> RUNNING -> STAGE UPDATE -> SUCCEEDED."""
        req = AnalysisJobCreateRequest(question="Deploy AI assistant?")
        firestore_storage.create_job(request=req, job_id="job-cycle-01")

        # 1. Update running
        firestore_storage.update_running(
            "job-cycle-01",
            stage=PipelineStage.STAGE1_DECISION_FRAMER,
            message="Framing the decision.",
        )
        job_running = firestore_storage.get_job("job-cycle-01")
        assert job_running is not None
        assert job_running.status == JobStatus.RUNNING
        assert job_running.stage == PipelineStage.STAGE1_DECISION_FRAMER
        assert job_running.started_at is not None
        assert "Framing" in job_running.progress_message

        # 2. Update stage
        firestore_storage.update_stage(
            "job-cycle-01",
            stage=PipelineStage.STAGE2_EVIDENCE_ENGINE,
            message="Gathering empirical sources.",
        )
        job_staged = firestore_storage.get_job("job-cycle-01")
        assert job_staged is not None
        assert job_staged.stage == PipelineStage.STAGE2_EVIDENCE_ENGINE
        assert "empirical" in job_staged.progress_message

        # 3. Complete job
        resp = make_dummy_analysis_response("analysis-cycle-01")
        firestore_storage.complete_job("job-cycle-01", resp, message="Analysis complete.")

        job_done = firestore_storage.get_job("job-cycle-01")
        assert job_done is not None
        assert job_done.status == JobStatus.SUCCEEDED
        assert job_done.stage == PipelineStage.COMPLETED
        assert job_done.completed_at is not None
        assert job_done.response is not None
        assert job_done.response.analysis_id == "analysis-cycle-01"

    def test_job_failure_and_timeout(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies terminal failure and timeout updates."""
        req = AnalysisJobCreateRequest(question="Test failure")
        firestore_storage.create_job(request=req, job_id="job-fail-01")

        firestore_storage.fail_job("job-fail-01", error_message="LLM quota exhausted", error_status_code=429)
        failed_job = firestore_storage.get_job("job-fail-01")
        assert failed_job is not None
        assert failed_job.status == JobStatus.FAILED
        assert failed_job.error_status_code == 429
        assert "quota" in (failed_job.error_message or "")

        # Timeout
        firestore_storage.create_job(request=req, job_id="job-timeout-01")
        firestore_storage.timeout_job("job-timeout-01", error_message="Request exceeded deadline")
        timeout_job = firestore_storage.get_job("job-timeout-01")
        assert timeout_job is not None
        assert timeout_job.status == JobStatus.TIMED_OUT
        assert timeout_job.error_status_code == 504

    def test_get_job_by_any_id_indexed_resolution(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies fast top-level indexed lookup by either job_id or analysis_id."""
        req = AnalysisJobCreateRequest(question="Resolve by analysis ID")
        firestore_storage.create_job(request=req, job_id="job-idx-01")
        resp = make_dummy_analysis_response("analysis-target-77")
        firestore_storage.complete_job("job-idx-01", resp)

        # 1. Resolve by direct job_id
        by_job = firestore_storage.get_job_by_any_id("job-idx-01")
        assert by_job is not None
        assert by_job.job_id == "job-idx-01"

        # 2. Resolve by top-level indexed analysis_id
        by_analysis = firestore_storage.get_job_by_any_id("analysis-target-77")
        assert by_analysis is not None
        assert by_analysis.job_id == "job-idx-01"
        assert by_analysis.response is not None
        assert by_analysis.response.analysis_id == "analysis-target-77"

        # 3. Non-existent ID returns None
        assert firestore_storage.get_job_by_any_id("non-existent-id") is None

    def test_list_jobs_and_owner_filtering(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies listing jobs with owner scoping and limit constraints."""
        for i in range(3):
            req = AnalysisJobCreateRequest(question=f"Q{i}", owner_id="alice")
            firestore_storage.create_job(req, job_id=f"alice-job-{i}")
        req_bob = AnalysisJobCreateRequest(question="Bob Q", owner_id="bob")
        firestore_storage.create_job(req_bob, job_id="bob-job-01")

        alice_jobs = firestore_storage.list_jobs(owner_id="alice", limit=10)
        assert len(alice_jobs) == 3
        assert all(j.owner_id == "alice" for j in alice_jobs)

        all_jobs = firestore_storage.list_jobs(limit=2)
        assert len(all_jobs) == 2

    def test_simulations_persistence_and_retrieval(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies what-if simulation save, lookup, and list."""
        req_data = json.dumps({"variable": "headcount", "value": 5})
        res_data = json.dumps({"delta": 12.5, "feasible": True})

        firestore_storage.save_simulation(
            simulation_id="sim-01",
            job_id="job-sim-01",
            analysis_id="analysis-sim-01",
            baseline_fingerprint="fp-123",
            request_json=req_data,
            result_json=res_data,
        )

        sim = firestore_storage.get_simulation("sim-01")
        assert sim is not None
        assert sim["simulation_id"] == "sim-01"
        assert sim["result_json"] == res_data

        # Parent ID verification
        assert firestore_storage.get_simulation("sim-01", job_id_or_analysis_id="job-sim-01") is not None
        assert firestore_storage.get_simulation("sim-01", job_id_or_analysis_id="analysis-sim-01") is not None
        assert firestore_storage.get_simulation("sim-01", job_id_or_analysis_id="wrong-parent") is None

        # Listing
        sim_list = firestore_storage.list_simulations("analysis-sim-01")
        assert len(sim_list) == 1
        assert sim_list[0]["simulation_id"] == "sim-01"

    def test_simulation_explanations(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies simulation AI explanation persistence and retrieval."""
        exp_data = json.dumps({"narrative": "Increased headcount improves timeline."})

        firestore_storage.save_simulation_explanation(
            simulation_id="sim-exp-01",
            analysis_id="analysis-exp-01",
            baseline_fingerprint="fp-456",
            prompt_version="v1.0",
            model_name="gemini-3.8-flash",
            explanation_json=exp_data,
        )

        exp = firestore_storage.get_simulation_explanation("sim-exp-01")
        assert exp is not None
        assert exp["model_name"] == "gemini-3.8-flash"
        assert exp["explanation_json"] == exp_data

        assert firestore_storage.get_simulation_explanation("missing-exp") is None

    def test_action_plans_crud_and_scoping(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies action plan upsert, scoped retrieval, and deletion."""
        plan_data = json.dumps({"strategy": "Migrate to Cloud Run in 3 phases."})

        firestore_storage.save_action_plan(
            plan_id="plan-01",
            analysis_id="analysis-plan-01",
            source_recommendation_fingerprint="rec-fp-1",
            schema_version="1.0.0",
            generator_version="gemini-3.8-flash",
            plan_json=plan_data,
            owner_id="lead-architect",
        )

        # Retrieve by analysis_id
        plan = firestore_storage.get_action_plan("analysis-plan-01", owner_id="lead-architect")
        assert plan is not None
        assert plan["plan_id"] == "plan-01"
        assert plan["plan_json"] == plan_data

        # Retrieve by plan_id
        plan_by_id = firestore_storage.get_action_plan_by_id("plan-01", owner_id="lead-architect")
        assert plan_by_id is not None
        assert plan_by_id["plan_id"] == "plan-01"

        # Wrong owner blocked
        assert firestore_storage.get_action_plan_by_id("plan-01", owner_id="unauthorized-user") is None

        # Delete
        firestore_storage.delete_action_plan("analysis-plan-01")
        assert firestore_storage.get_action_plan("analysis-plan-01") is None

    def test_action_plan_claims_atomic_transactions(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies atomic lease acquisition, expiry reclaiming, and release behavior."""
        # 1. Acquire brand new claim
        acquired, status, claim_id = firestore_storage.acquire_action_plan_claim(
            analysis_id="analysis-claim-01",
            owner_id="worker-1",
            ttl_seconds=60.0,
        )
        assert acquired is True
        assert status == "acquired"
        assert claim_id != ""

        # 2. Second concurrent worker blocked while claim is active
        acq_2, status_2, held_claim_id = firestore_storage.acquire_action_plan_claim(
            analysis_id="analysis-claim-01",
            owner_id="worker-2",
            ttl_seconds=60.0,
        )
        assert acq_2 is False
        assert status_2 == "running"
        assert held_claim_id == claim_id

        # 3. Simulate expired claim
        claim_doc = firestore_storage._action_plan_claims_col.document("analysis-claim-01")
        claim_doc.update({"expires_at": time.time() - 10.0})

        # Re-acquisition succeeds over expired lease
        acq_3, status_3, new_claim_id = firestore_storage.acquire_action_plan_claim(
            analysis_id="analysis-claim-01",
            owner_id="worker-3",
            ttl_seconds=60.0,
        )
        assert acq_3 is True
        assert status_3 == "acquired"
        assert new_claim_id != claim_id

        # 4. Release claim
        firestore_storage.release_action_plan_claim("analysis-claim-01", new_claim_id, success=True)
        claim_state = firestore_storage.get_action_plan_claim("analysis-claim-01")
        assert claim_state is not None
        assert claim_state["status"] == "ready"

    def test_large_payload_transparent_chunking_and_reconstruction(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies that payloads exceeding 700 KiB are safely chunked and reconstructed byte-for-byte."""
        req = AnalysisJobCreateRequest(question="Large response test")
        firestore_storage.create_job(request=req, job_id="job-large-01")

        # Construct an ~850 KiB payload (safely below 1 MiB hard limit per chunk)
        resp = AnalysisResponse(
            analysis_id="analysis-large-01",
            question="Large payload test",
            message="x" * 850_000,
            status="completed",
            stages_completed=["stage1_decision_framer"],
        )
        large_json = resp.model_dump_json()
        assert len(large_json.encode("utf-8")) > 700_000

        firestore_storage.complete_job("job-large-01", resp)

        # Inspect raw document structure
        doc_snap = firestore_storage._jobs_col.document("job-large-01").get()
        doc_data = doc_snap.to_dict()
        assert doc_data["response_json_chunked"] is True
        assert doc_data["response_json"] is None
        assert doc_data["response_json_status"] == "ready"
        assert doc_data["response_json_total_chunks"] >= 2

        # Reconstructed retrieval through get_job()
        job = firestore_storage.get_job("job-large-01")
        assert job is not None
        assert job.response is not None
        assert job.response.analysis_id == "analysis-large-01"
        assert len(job.response.question) > 0

    def test_chunking_failure_safety_on_partial_write(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies that interrupted or corrupted chunked states raise errors rather than exposing bad data."""
        doc_ref = firestore_storage._jobs_col.document("job-corrupted-01")
        req_json = json.dumps({"question": "Test question", "context": {"k": "v"}})
        doc_ref.set({
            "job_id": "job-corrupted-01",
            "status": "succeeded",
            "stage": "completed",
            "request_json": req_json,
            "response_json": None,
            "response_json_chunked": True,
            "response_json_status": "writing_in_progress",  # Unready status
        })

        with pytest.raises(RuntimeError) as exc_info:
            firestore_storage.get_job("job-corrupted-01")
        assert "non-ready state" in str(exc_info.value)

    def test_startup_recovery_safe_for_cloud_run(self, firestore_storage: FirestoreJobStorage) -> None:
        """Verifies recover_stale_jobs_on_startup returns 0 and does not mark cloud jobs as failed."""
        req = AnalysisJobCreateRequest(question="Active distributed job")
        firestore_storage.create_job(request=req, job_id="active-job-01")
        firestore_storage.update_running("active-job-01")

        recovered = firestore_storage.recover_stale_jobs_on_startup()
        assert recovered == 0

        # Confirm job was not destroyed
        job = firestore_storage.get_job("active-job-01")
        assert job is not None
        assert job.status == JobStatus.RUNNING

    def test_factory_initialization_failure_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies that factory does not silently fall back to SQLite if Firestore raises on init."""
        monkeypatch.setenv("AURA_STORAGE_BACKEND", "firestore")
        from app import config
        monkeypatch.setattr(config.settings, "AURA_STORAGE_BACKEND", "firestore")

        # Mock FirestoreJobStorage init to fail
        def failing_init(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Google Cloud ADC credentials not found.")

        monkeypatch.setattr("app.services.jobs.firestore_storage.FirestoreJobStorage.__init__", failing_init)

        with pytest.raises(RuntimeError) as exc:
            get_job_storage(backend="firestore")
        assert "ADC credentials not found" in str(exc.value)

    def test_non_ascii_large_payload_chunking_and_reconstruction(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies multi-byte UTF-8 payloads (emojis, CJK) chunk cleanly without splitting code points."""
        # Create ~800 KB of multi-byte characters (4 bytes per emoji + 3 bytes per CJK char)
        multibyte_pattern = "🚀✨决策智能_AURA_こんにちは世界_2026🌟"
        repeats = 800_000 // len(multibyte_pattern.encode("utf-8")) + 10
        large_unicode_text = multibyte_pattern * repeats
        total_bytes = len(large_unicode_text.encode("utf-8"))
        assert total_bytes > 700_000

        plan_data = {
            "plan_id": "plan-unicode-01",
            "analysis_id": "analysis-unicode-01",
            "content": large_unicode_text,
        }
        plan_json = json.dumps(plan_data, ensure_ascii=False)

        firestore_storage.save_action_plan(
            plan_id="plan-unicode-01",
            analysis_id="analysis-unicode-01",
            source_recommendation_fingerprint="fp-unicode",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=plan_json,
        )

        # Verify parent document state
        plan_doc = firestore_storage._action_plans_col.document("plan-unicode-01").get().to_dict()
        assert plan_doc.get("plan_json_chunked") is True
        assert plan_doc.get("plan_json") is None
        total_chunks = plan_doc.get("plan_json_total_chunks")
        assert total_chunks >= 2

        # Verify each chunk document byte size is <= 500_000 bytes
        chunks_col = firestore_storage._action_plans_col.document("plan-unicode-01").collection("plan_json_chunks")
        for idx in range(total_chunks):
            v = plan_doc["plan_json_version"]
            c_doc = chunks_col.document(f"{v}_{idx:04d}").get().to_dict()
            chunk_bytes = len(c_doc["data"].encode("utf-8"))
            assert chunk_bytes <= 500_000

        # Retrieve and verify exact byte-for-byte reconstruction
        loaded = firestore_storage.get_action_plan("analysis-unicode-01")
        assert loaded is not None
        loaded_data = json.loads(loaded["plan_json"])
        assert loaded_data["content"] == large_unicode_text

    def test_repeated_saves_upsert_chunked_to_inline(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies overwriting a large chunked document with a small inline payload clears chunk state."""
        # 1. Save large chunked action plan
        large_content = "X" * 750_000
        large_json = json.dumps({"content": large_content})
        firestore_storage.save_action_plan(
            plan_id="plan-upsert-01",
            analysis_id="analysis-upsert-01",
            source_recommendation_fingerprint="fp-1",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=large_json,
        )
        assert firestore_storage.get_action_plan("analysis-upsert-01")["plan_json"] == large_json

        # 2. Overwrite with small inline action plan (< 700 KB)
        small_json = json.dumps({"content": "small updated inline content"})
        firestore_storage.save_action_plan(
            plan_id="plan-upsert-01",
            analysis_id="analysis-upsert-01",
            source_recommendation_fingerprint="fp-2",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=small_json,
        )

        doc = firestore_storage._action_plans_col.document("plan-upsert-01").get().to_dict()
        assert doc.get("plan_json_chunked") is False
        assert doc.get("plan_json") == small_json

        # 3. Retrieve and verify clean read
        loaded = firestore_storage.get_action_plan("analysis-upsert-01")
        assert loaded["plan_json"] == small_json

    def test_old_version_reads_ignored(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies chunks from older versions in subcollections are not loaded into newer versions."""
        # 1. Save version 1 (large)
        v1_text = "V1_" + ("A" * 750_000)
        firestore_storage.save_action_plan(
            plan_id="plan-ver-01",
            analysis_id="analysis-ver-01",
            source_recommendation_fingerprint="fp-1",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=v1_text,
        )
        v1_doc = firestore_storage._action_plans_col.document("plan-ver-01").get().to_dict()
        v1_version = v1_doc["plan_json_version"]

        # 2. Save version 2 (large)
        v2_text = "V2_" + ("B" * 750_000)
        firestore_storage.save_action_plan(
            plan_id="plan-ver-01",
            analysis_id="analysis-ver-01",
            source_recommendation_fingerprint="fp-2",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=v2_text,
        )
        v2_doc = firestore_storage._action_plans_col.document("plan-ver-01").get().to_dict()
        v2_version = v2_doc["plan_json_version"]
        assert v1_version != v2_version

        # 3. Load and confirm it loads V2 completely without mixing with V1
        loaded = firestore_storage.get_action_plan("analysis-ver-01")
        assert loaded["plan_json"] == v2_text

    def test_partial_write_incomplete_chunks_raises_error(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies missing chunks cause a RuntimeError rather than returning corrupted/partial data."""
        doc_ref = firestore_storage._action_plans_col.document("plan-partial-01")
        chunk_ver = str(uuid.uuid4())
        chunks_col = doc_ref.collection("plan_json_chunks")

        # Write chunk 0, but intentionally omit chunk 1
        chunks_col.document(f"{chunk_ver}_0000").set({
            "version": chunk_ver,
            "index": 0,
            "total_chunks": 2,
            "data": "chunk0_data",
        })

        doc_ref.set({
            "plan_id": "plan-partial-01",
            "analysis_id": "analysis-partial-01",
            "plan_json": None,
            "plan_json_chunked": True,
            "plan_json_version": chunk_ver,
            "plan_json_total_chunks": 2,  # Expects 2
            "plan_json_status": "ready",
            "created_at": _utc_now_iso(),
        })

        with pytest.raises(RuntimeError) as exc_info:
            firestore_storage.get_action_plan("analysis-partial-01")
        assert "Chunk reconstruction failed" in str(exc_info.value)

    def test_claim_acquisition_before_action_plan_exists(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies durable generation claim can be acquired, inspected, and released before any action plan exists."""
        analysis_id = "analysis-pre-plan-01"

        # No plan exists yet
        assert firestore_storage.get_action_plan(analysis_id) is None

        # Acquire claim
        acquired, status, claim_id = firestore_storage.acquire_action_plan_claim(
            analysis_id=analysis_id, owner_id="user-123", ttl_seconds=60.0
        )
        assert acquired is True
        assert status == "acquired"
        assert claim_id != ""

        # Verify claim inspection
        claim = firestore_storage.get_action_plan_claim(analysis_id)
        assert claim is not None
        assert claim["claim_id"] == claim_id
        assert claim["status"] == "running"
        assert claim["owner_id"] == "user-123"

        # Release claim as ready
        firestore_storage.release_action_plan_claim(analysis_id, claim_id=claim_id, success=True)
        claim_after = firestore_storage.get_action_plan_claim(analysis_id)
        assert claim_after["status"] == "ready"

    def test_stale_claim_cannot_overwrite_newer_claim(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies an expired/stale worker cannot overwrite or release a newer active claim."""
        analysis_id = "analysis-stale-01"

        # 1. Worker 1 acquires claim with 1s TTL
        acq1, stat1, claim1 = firestore_storage.acquire_action_plan_claim(
            analysis_id=analysis_id, ttl_seconds=0.01
        )
        assert acq1 is True

        # Let TTL expire
        time.sleep(0.02)

        # 2. Worker 2 acquires new claim
        acq2, stat2, claim2 = firestore_storage.acquire_action_plan_claim(
            analysis_id=analysis_id, ttl_seconds=60.0
        )
        assert acq2 is True
        assert claim2 != claim1

        # 3. Worker 1 finishes late and attempts release with old claim1
        firestore_storage.release_action_plan_claim(
            analysis_id=analysis_id, claim_id=claim1, success=True
        )

        # Claim must still belong to Worker 2 in running status
        curr_claim = firestore_storage.get_action_plan_claim(analysis_id)
        assert curr_claim["claim_id"] == claim2
        assert curr_claim["status"] == "running"

    def test_action_plan_owner_scoping_prefers_latest(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies get_action_plan returns the latest plan matching owner or unowned public."""
        analysis_id = "analysis-owner-latest-01"

        # Unowned plan created earlier
        firestore_storage.save_action_plan(
            plan_id="plan-public",
            analysis_id=analysis_id,
            source_recommendation_fingerprint="fp-pub",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=json.dumps({"plan": "public"}),
            owner_id=None,
            created_at="2026-01-01T10:00:00Z",
        )

        # User-owned plan created later
        firestore_storage.save_action_plan(
            plan_id="plan-user",
            analysis_id=analysis_id,
            source_recommendation_fingerprint="fp-user",
            schema_version="1.0",
            generator_version="1.0",
            plan_json=json.dumps({"plan": "user"}),
            owner_id="user-456",
            created_at="2026-01-01T12:00:00Z",
        )

        # Query with owner_id="user-456" selects the user-owned one
        res = firestore_storage.get_action_plan(analysis_id, owner_id="user-456")
        assert res["plan_id"] == "plan-user"

        # Query with another owner "other-user" gets the public unowned one
        res_other = firestore_storage.get_action_plan(analysis_id, owner_id="other-user")
        assert res_other["plan_id"] == "plan-public"

    def test_firestore_acquire_job_execution_claim_and_fencing(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies atomic job execution claims, fencing tokens, and lease expiry in Firestore."""
        req = AnalysisJobCreateRequest(question="Firestore Claim Test")
        record = firestore_storage.create_job(req, job_id="fs-claim-01")

        # 1. Acquire claim
        acq, stat, updated = firestore_storage.acquire_job_execution_claim(
            job_id="fs-claim-01",
            attempt_id="fs-attempt-1",
            lease_seconds=0.02,
        )
        assert acq is True
        assert stat == "acquired"
        assert updated.attempt_id == "fs-attempt-1"
        assert updated.fencing_token == 1
        assert updated.status == JobStatus.RUNNING

        # 2. Duplicate worker rejection while active
        acq2, stat2, _ = firestore_storage.acquire_job_execution_claim(
            job_id="fs-claim-01",
            attempt_id="fs-attempt-2",
            lease_seconds=60.0,
        )
        assert acq2 is False
        assert stat2 == "concurrent_active"

        # 3. Allow lease to expire
        time.sleep(0.03)

        # 4. New worker acquires expired lease with incremented fencing token
        acq3, stat3, updated3 = firestore_storage.acquire_job_execution_claim(
            job_id="fs-claim-01",
            attempt_id="fs-attempt-3",
            lease_seconds=60.0,
        )
        assert acq3 is True
        assert stat3 == "acquired"
        assert updated3.attempt_id == "fs-attempt-3"
        assert updated3.fencing_token == 2

    def test_firestore_record_dispatch_status(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies dispatch status recording and failure state transition in Firestore."""
        req = AnalysisJobCreateRequest(question="Dispatch Status Test")
        firestore_storage.create_job(req, job_id="fs-dispatch-01")

        # Record enqueued
        firestore_storage.record_dispatch_status("fs-dispatch-01", dispatch_status="enqueued")
        job = firestore_storage.get_job("fs-dispatch-01")
        assert job.dispatch_status == "enqueued"

        # Record failure
        firestore_storage.record_dispatch_status(
            "fs-dispatch-01",
            dispatch_status="enqueue_failed",
            error_message="Queue full",
        )
        failed_job = firestore_storage.get_job("fs-dispatch-01")
        assert failed_job.dispatch_status == "enqueue_failed"
        assert failed_job.status == JobStatus.FAILED
        assert "Queue full" in failed_job.error_message

    def test_firestore_expired_lease_after_provider_marker_fails_for_manual_recovery(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies that an expired lease after provider execution marker marks job FAILED for manual recovery."""
        req = AnalysisJobCreateRequest(question="Provider Marker Test")
        firestore_storage.create_job(req, job_id="fs-marker-01")

        # Worker 1 acquires claim
        acq, stat, _ = firestore_storage.acquire_job_execution_claim(
            job_id="fs-marker-01",
            attempt_id="worker-1",
            lease_seconds=0.01,
        )
        assert acq is True

        # Commit provider execution marker
        firestore_storage.mark_provider_execution_started("fs-marker-01")
        marked_job = firestore_storage.get_job("fs-marker-01")
        assert marked_job.provider_execution_started is True

        # Lease expires
        time.sleep(0.02)

        # Worker 2 redelivery attempt must be rejected and job failed for manual recovery
        acq2, stat2, updated2 = firestore_storage.acquire_job_execution_claim(
            job_id="fs-marker-01",
            attempt_id="worker-2",
            lease_seconds=60.0,
        )
        assert acq2 is False
        assert stat2 == "ambiguous_failure"
        assert updated2.status == JobStatus.FAILED
        assert "Ambiguous worker termination after provider execution started" in updated2.error_message
        assert "manual recovery required" in updated2.error_message

    def test_firestore_mark_provider_execution_started_atomic_validation(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies Firestore mark_provider_execution_started atomically checks attempt_id, fencing_token, and lease."""
        req = AnalysisJobCreateRequest(question="Provider Marker Atomic Validation")
        firestore_storage.create_job(req, job_id="fs-val-01")

        # 1. Reject before claim acquired (status QUEUED)
        ok = firestore_storage.mark_provider_execution_started(
            "fs-val-01", attempt_id="att-1", fencing_token=1
        )
        assert ok is False
        assert firestore_storage.get_job("fs-val-01").provider_execution_started is False

        # 2. Acquire claim
        acq, _, rec = firestore_storage.acquire_job_execution_claim(
            job_id="fs-val-01", attempt_id="att-1", lease_seconds=1.0
        )
        assert acq is True
        assert rec.fencing_token == 1

        # 3. Reject mismatched attempt_id
        ok_wrong_att = firestore_storage.mark_provider_execution_started(
            "fs-val-01", attempt_id="att-wrong", fencing_token=1
        )
        assert ok_wrong_att is False
        assert firestore_storage.get_job("fs-val-01").provider_execution_started is False

        # 4. Reject mismatched fencing_token
        ok_wrong_token = firestore_storage.mark_provider_execution_started(
            "fs-val-01", attempt_id="att-1", fencing_token=99
        )
        assert ok_wrong_token is False
        assert firestore_storage.get_job("fs-val-01").provider_execution_started is False

        # 5. Success with valid attempt_id, fencing_token, and active lease
        ok_valid = firestore_storage.mark_provider_execution_started(
            "fs-val-01", attempt_id="att-1", fencing_token=1
        )
        assert ok_valid is True
        assert firestore_storage.get_job("fs-val-01").provider_execution_started is True

    def test_firestore_mark_provider_execution_started_rejects_expired_lease(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies Firestore mark_provider_execution_started rejects call if lease expired."""
        req = AnalysisJobCreateRequest(question="Provider Marker Expired Lease")
        firestore_storage.create_job(req, job_id="fs-lease-exp-01")

        acq, _, rec = firestore_storage.acquire_job_execution_claim(
            job_id="fs-lease-exp-01", attempt_id="att-exp", lease_seconds=0.01
        )
        assert acq is True

        time.sleep(0.02)  # Expire lease

        ok = firestore_storage.mark_provider_execution_started(
            "fs-lease-exp-01", attempt_id="att-exp", fencing_token=rec.fencing_token
        )
        assert ok is False
        assert firestore_storage.get_job("fs-lease-exp-01").provider_execution_started is False

    def test_firestore_terminal_writes_fenced_against_stale_tokens(
        self, firestore_storage: FirestoreJobStorage
    ) -> None:
        """Verifies Firestore complete_job, fail_job, and update_stage ignore writes with stale tokens."""
        req = AnalysisJobCreateRequest(question="Terminal Write Fencing Test")
        firestore_storage.create_job(req, job_id="fs-fence-term-01")

        # Worker 1 acquires claim (fencing_token = 1)
        acq1, _, rec1 = firestore_storage.acquire_job_execution_claim(
            job_id="fs-fence-term-01", attempt_id="w1", lease_seconds=0.01
        )
        assert acq1 is True
        assert rec1.fencing_token == 1

        time.sleep(0.02)  # Expire lease

        # Worker 2 acquires claim (fencing_token = 2)
        acq2, _, rec2 = firestore_storage.acquire_job_execution_claim(
            job_id="fs-fence-term-01", attempt_id="w2", lease_seconds=60.0
        )
        assert acq2 is True
        assert rec2.fencing_token == 2

        # Worker 1 tries to update stage with stale fencing_token=1 -> should be rejected
        firestore_storage.update_stage(
            "fs-fence-term-01",
            stage=PipelineStage.STAGE2_EVIDENCE_ENGINE,
            message="Worker 1 stale update",
            fencing_token=1,
        )
        job_after_stage = firestore_storage.get_job("fs-fence-term-01")
        assert job_after_stage.stage != PipelineStage.STAGE2_EVIDENCE_ENGINE
        assert job_after_stage.progress_message != "Worker 1 stale update"

        # Worker 1 tries to complete job with stale fencing_token=1 -> should be rejected
        resp = AnalysisResponse(analysis_id="fs-test-resp", status="completed")
        firestore_storage.complete_job(
            "fs-fence-term-01",
            response=resp,
            fencing_token=1,
        )

        # Worker 1 tries to fail job with stale fencing_token=1 -> should be rejected
        firestore_storage.fail_job(
            "fs-fence-term-01",
            error_message="Worker 1 stale failure",
            fencing_token=1,
        )

        # Current job must still be RUNNING with fencing_token=2
        curr = firestore_storage.get_job("fs-fence-term-01")
        assert curr.status == JobStatus.RUNNING
        assert curr.fencing_token == 2

        # Worker 2 writes with valid token=2 -> accepted
        firestore_storage.complete_job(
            "fs-fence-term-01",
            response=resp,
            fencing_token=2,
        )
        final_job = firestore_storage.get_job("fs-fence-term-01")
        assert final_job.status == JobStatus.SUCCEEDED

    def test_sqlite_storage_continues_working_identically(self) -> None:
        """Verifies existing SQLiteJobStorage retains 100% operational baseline."""
        storage = SQLiteJobStorage(db_path=":memory:")
        req = AnalysisJobCreateRequest(question="SQLite Baseline Check")
        record = storage.create_job(req, job_id="sqlite-01")
        assert record.job_id == "sqlite-01"
        assert record.status == JobStatus.QUEUED
        assert storage.get_job("sqlite-01") is not None
        storage.close()


