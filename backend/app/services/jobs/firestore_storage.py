"""AURA Google Cloud Firestore Job Storage.

Provides enterprise-ready, Native-mode Firestore persistence for asynchronous
analysis jobs, what-if simulations, explanations, action plans, and durable
distributed generation claims.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.config import settings
from app.schemas.analysis import AnalysisResponse
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage
from app.services.jobs.base import JobRecord, JobStorageInterface

logger = logging.getLogger(__name__)

# Conservative byte threshold: documents with payloads exceeding 700 KiB are
# safely chunked to guarantee compliance with Firestore's 1,048,576 byte hard limit.
MAX_INLINE_PAYLOAD_BYTES = 700_000
MAX_CHUNK_BYTES = 500_000


def _utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _chunk_text_by_utf8_bytes(text: str, max_bytes_per_chunk: int = MAX_CHUNK_BYTES) -> List[str]:
    """Splits a Unicode string into chunks where each chunk's UTF-8 byte size <= max_bytes_per_chunk.
    
    Guarantees no multi-byte Unicode code points are split across chunk boundaries,
    preventing UTF-8 corruption while respecting hard byte limits.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes_per_chunk:
        return [text]

    chunks: List[str] = []
    start_byte = 0
    total_bytes = len(encoded)
    while start_byte < total_bytes:
        end_byte = min(start_byte + max_bytes_per_chunk, total_bytes)
        # Backtrack if end_byte lands on a UTF-8 continuation byte (0x80 to 0xBF)
        while end_byte > start_byte and end_byte < total_bytes and (encoded[end_byte] & 0xC0) == 0x80:
            end_byte -= 1
        chunk_str = encoded[start_byte:end_byte].decode("utf-8")
        chunks.append(chunk_str)
        start_byte = end_byte
    return chunks


class FirestoreJobStorage(JobStorageInterface):
    """Production-grade Firestore Native storage adapter for AURA decision intelligence."""

    def __init__(
        self,
        project: Optional[str] = None,
        database: Optional[str] = None,
        client: Optional[firestore.Client] = None,
    ) -> None:
        """Initializes Firestore client using explicit injection or Application Default Credentials.

        Args:
            project: Google Cloud project ID (defaults to settings.GOOGLE_CLOUD_PROJECT or env).
            database: Firestore database ID (defaults to settings.FIRESTORE_DATABASE or '(default)').
            client: Optional pre-configured firestore.Client instance (used for offline tests/mocks).
        """
        self.project = project or getattr(settings, "GOOGLE_CLOUD_PROJECT", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.database = database or getattr(settings, "FIRESTORE_DATABASE", "(default)")

        if client is not None:
            self._db = client
        else:
            try:
                client_kwargs: Dict[str, Any] = {"database": self.database}
                if self.project:
                    client_kwargs["project"] = self.project
                self._db = firestore.Client(**client_kwargs)
            except Exception as exc:
                logger.error("Failed to initialize Google Cloud Firestore client: %s", exc)
                raise RuntimeError(
                    f"Could not initialize Firestore storage adapter for database '{self.database}'. "
                    f"Ensure credentials or Google Application Default Credentials are valid: {exc}"
                ) from exc

        # Collections
        self._jobs_col = self._db.collection("jobs")
        self._simulations_col = self._db.collection("simulations")
        self._simulation_explanations_col = self._db.collection("simulation_explanations")
        self._action_plans_col = self._db.collection("action_plans")
        self._action_plan_claims_col = self._db.collection("action_plan_claims")

    # -------------------------------------------------------------------------
    # Chunking & Large Payload Safety
    # -------------------------------------------------------------------------

    def _store_chunkable_payload(
        self,
        doc_ref: Any,
        field_name: str,
        payload_str: Optional[str],
        base_data: Dict[str, Any],
        update_only: bool = False,
    ) -> None:
        """Stores a document with transparent chunking if payload exceeds safe byte limit."""
        if payload_str is None:
            data = {
                **base_data,
                field_name: None,
                f"{field_name}_chunked": False,
                f"{field_name}_version": None,
                f"{field_name}_total_chunks": 0,
                f"{field_name}_status": "ready",
            }
            if update_only:
                doc_ref.update(data)
            else:
                doc_ref.set(data)
            return

        payload_bytes = payload_str.encode("utf-8")
        if len(payload_bytes) <= MAX_INLINE_PAYLOAD_BYTES:
            data = {
                **base_data,
                field_name: payload_str,
                f"{field_name}_chunked": False,
                f"{field_name}_version": None,
                f"{field_name}_total_chunks": 0,
                f"{field_name}_status": "ready",
            }
            if update_only:
                doc_ref.update(data)
            else:
                doc_ref.set(data)
            return

        # Large payload handling with UTF-8 byte boundary safety
        chunk_version = str(uuid.uuid4())
        chunks = _chunk_text_by_utf8_bytes(payload_str, MAX_CHUNK_BYTES)
        total_chunks = len(chunks)
        chunks_col = doc_ref.collection(f"{field_name}_chunks")

        # 1. Write all chunks under the unique version
        for idx, chunk_content in enumerate(chunks):
            chunk_doc_id = f"{chunk_version}_{idx:04d}"
            chunk_ref = chunks_col.document(chunk_doc_id)
            chunk_ref.set({
                "version": chunk_version,
                "index": idx,
                "total_chunks": total_chunks,
                "data": chunk_content,
                "created_at": _utc_now_iso(),
            })

        # 2. Publish parent document referencing the completed chunk version
        data = {
            **base_data,
            field_name: None,
            f"{field_name}_chunked": True,
            f"{field_name}_version": chunk_version,
            f"{field_name}_total_chunks": total_chunks,
            f"{field_name}_size_bytes": len(payload_bytes),
            f"{field_name}_status": "ready",
        }
        if update_only:
            doc_ref.update(data)
        else:
            doc_ref.set(data)

    def _load_chunkable_payload(
        self,
        doc_ref: Any,
        doc_data: Dict[str, Any],
        field_name: str,
    ) -> Optional[str]:
        """Loads a document payload, seamlessly reassembling chunks if chunked."""
        if not doc_data.get(f"{field_name}_chunked"):
            return doc_data.get(field_name)

        chunk_status = doc_data.get(f"{field_name}_status")
        if chunk_status != "ready":
            raise RuntimeError(
                f"Payload for '{field_name}' in document '{doc_ref.id}' is in non-ready state '{chunk_status}'."
            )

        version = doc_data.get(f"{field_name}_version")
        expected_total = doc_data.get(f"{field_name}_total_chunks", 0)
        chunks_col = doc_ref.collection(f"{field_name}_chunks")

        query = chunks_col.where(filter=FieldFilter("version", "==", version))
        chunk_docs = list(query.stream())

        if len(chunk_docs) != expected_total:
            raise RuntimeError(
                f"Chunk reconstruction failed for '{field_name}' in doc '{doc_ref.id}'. "
                f"Expected {expected_total} chunks, but retrieved {len(chunk_docs)}."
            )

        # Sort in-memory by index to avoid requiring composite indexes on subcollections
        chunk_docs.sort(key=lambda d: d.to_dict().get("index", 0))

        assembled_chunks = [d.to_dict().get("data", "") for d in chunk_docs]
        reconstructed = "".join(assembled_chunks)
        return reconstructed

    # -------------------------------------------------------------------------
    # Core Analysis Jobs
    # -------------------------------------------------------------------------

    def create_job(
        self,
        request: AnalysisJobCreateRequest,
        job_id: Optional[str] = None,
        default_timeout_seconds: float = 180.0,
    ) -> JobRecord:
        """Persists a new job in QUEUED status."""
        jid = job_id or str(uuid.uuid4())
        created_at = _utc_now_iso()
        timeout_sec = request.timeout_seconds or default_timeout_seconds
        initial_msg = "Job submitted and queued for execution."
        req_json = request.model_dump_json()

        base_data: Dict[str, Any] = {
            "job_id": jid,
            "analysis_id": None,
            "status": JobStatus.QUEUED.value,
            "stage": PipelineStage.QUEUED.value,
            "error_message": None,
            "error_status_code": None,
            "owner_id": request.owner_id,
            "created_at": created_at,
            "started_at": None,
            "completed_at": None,
            "timeout_seconds": float(timeout_sec),
            "framer_timeout_seconds": float(request.framer_operation_timeout_seconds) if request.framer_operation_timeout_seconds is not None else None,
            "boardroom_timeout_seconds": float(request.boardroom_operation_timeout_seconds) if request.boardroom_operation_timeout_seconds is not None else None,
            "recommendation_timeout_seconds": float(request.recommendation_operation_timeout_seconds) if request.recommendation_operation_timeout_seconds is not None else None,
            "scenario_timeout_seconds": float(request.scenario_operation_timeout_seconds) if request.scenario_operation_timeout_seconds is not None else None,
            "progress_message": initial_msg,
            "response_json": None,
            "response_json_chunked": False,
            "attempt_id": None,
            "lease_expires_at": None,
            "fencing_token": 0,
            "dispatch_status": "pending",
            "dispatch_error": None,
            "provider_execution_started": False,
        }

        doc_ref = self._jobs_col.document(jid)
        self._store_chunkable_payload(doc_ref, "request_json", req_json, base_data)

        return JobRecord(
            job_id=jid,
            status=JobStatus.QUEUED,
            stage=PipelineStage.QUEUED,
            request=request,
            response=None,
            error_message=None,
            error_status_code=None,
            owner_id=request.owner_id,
            created_at=created_at,
            started_at=None,
            completed_at=None,
            timeout_seconds=float(timeout_sec),
            framer_timeout_seconds=request.framer_operation_timeout_seconds,
            boardroom_timeout_seconds=request.boardroom_operation_timeout_seconds,
            recommendation_timeout_seconds=request.recommendation_operation_timeout_seconds,
            scenario_timeout_seconds=request.scenario_operation_timeout_seconds,
            progress_message=initial_msg,
        )

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieves a job by its unique identifier."""
        doc_ref = self._jobs_col.document(job_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        return self._snapshot_to_record(doc_ref, snapshot.to_dict())

    def get_job_by_any_id(self, id_str: str) -> Optional[JobRecord]:
        """Resolves a JobRecord by either job_id directly or by indexed analysis_id."""
        # 1. Direct point lookup by job_id
        direct = self.get_job(id_str)
        if direct is not None:
            return direct

        # 2. Fast indexed query on top-level analysis_id
        query = self._jobs_col.where(filter=FieldFilter("analysis_id", "==", id_str)).limit(1)
        docs = list(query.stream())
        if docs:
            doc_ref = docs[0].reference
            return self._snapshot_to_record(doc_ref, docs[0].to_dict())

        return None

    def update_running(
        self,
        job_id: str,
        stage: PipelineStage = PipelineStage.STAGE1_DECISION_FRAMER,
        message: str = "Execution started.",
    ) -> None:
        """Transitions job to RUNNING status with start timestamp."""
        doc_ref = self._jobs_col.document(job_id)
        doc_ref.update({
            "status": JobStatus.RUNNING.value,
            "stage": stage.value,
            "started_at": _utc_now_iso(),
            "progress_message": message,
        })

    def update_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        message: str,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Updates pipeline stage and progress message while job remains RUNNING."""
        doc_ref = self._jobs_col.document(job_id)
        if fencing_token is not None:
            snap = doc_ref.get()
            if snap.exists:
                curr_token = int(snap.to_dict().get("fencing_token", 0) or 0)
                if curr_token != fencing_token:
                    logger.warning(
                        "Fenced update_stage rejected in Firestore for job %s: current token %d != caller %d",
                        job_id,
                        curr_token,
                        fencing_token,
                    )
                    return

        doc_ref.update({
            "stage": stage.value,
            "progress_message": message,
        })

    def complete_job(
        self,
        job_id: str,
        response: AnalysisResponse,
        message: str = "Analysis completed successfully.",
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to SUCCEEDED status with full validated response payload."""
        doc_ref = self._jobs_col.document(job_id)
        if fencing_token is not None:
            snap = doc_ref.get()
            if snap.exists:
                curr_token = int(snap.to_dict().get("fencing_token", 0) or 0)
                if curr_token != fencing_token:
                    logger.warning(
                        "Fenced complete_job rejected in Firestore for job %s: current token %d != caller %d",
                        job_id,
                        curr_token,
                        fencing_token,
                    )
                    return

        resp_json = response.model_dump_json()
        analysis_id = response.analysis_id

        # Update metadata fields
        update_data: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "status": JobStatus.SUCCEEDED.value,
            "stage": PipelineStage.COMPLETED.value,
            "completed_at": _utc_now_iso(),
            "progress_message": message,
        }

        # Store response_json with unified chunking safety
        self._store_chunkable_payload(doc_ref, "response_json", resp_json, update_data, update_only=True)

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_status_code: int = 500,
        stage: PipelineStage = PipelineStage.FAILED,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to FAILED status with error details."""
        doc_ref = self._jobs_col.document(job_id)
        if fencing_token is not None:
            snap = doc_ref.get()
            if snap.exists:
                curr_token = int(snap.to_dict().get("fencing_token", 0) or 0)
                if curr_token != fencing_token:
                    logger.warning(
                        "Fenced fail_job rejected in Firestore for job %s: current token %d != caller %d",
                        job_id,
                        curr_token,
                        fencing_token,
                    )
                    return

        doc_ref.update({
            "status": JobStatus.FAILED.value,
            "stage": stage.value,
            "error_message": error_message,
            "error_status_code": int(error_status_code),
            "completed_at": _utc_now_iso(),
            "progress_message": f"Job failed: {error_message}",
        })

    def timeout_job(
        self,
        job_id: str,
        error_message: str = "Decision analysis timed out while evaluating the inquiry.",
        stage: PipelineStage = PipelineStage.TIMED_OUT,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to TIMED_OUT status."""
        doc_ref = self._jobs_col.document(job_id)
        if fencing_token is not None:
            snap = doc_ref.get()
            if snap.exists:
                curr_token = int(snap.to_dict().get("fencing_token", 0) or 0)
                if curr_token != fencing_token:
                    logger.warning(
                        "Fenced timeout_job rejected in Firestore for job %s: current token %d != caller %d",
                        job_id,
                        curr_token,
                        fencing_token,
                    )
                    return

        doc_ref.update({
            "status": JobStatus.TIMED_OUT.value,
            "stage": stage.value,
            "error_message": error_message,
            "error_status_code": 504,
            "completed_at": _utc_now_iso(),
            "progress_message": f"Job timed out: {error_message}",
        })

    def acquire_job_execution_claim(
        self,
        job_id: str,
        attempt_id: str,
        lease_seconds: float = 300.0,
    ) -> Tuple[bool, str, Optional[JobRecord]]:
        """Atomically acquires an execution claim for a job with fencing token in Firestore."""
        doc_ref = self._jobs_col.document(job_id)

        @firestore.transactional
        def _txn_claim(transaction: Any) -> Tuple[bool, str, Optional[JobRecord]]:
            snapshot = doc_ref.get(transaction=transaction)
            if not snapshot.exists:
                return False, "not_found", None

            data = snapshot.to_dict()
            curr_status = data.get("status")
            if curr_status == JobStatus.SUCCEEDED.value:
                return False, "already_completed", self._snapshot_to_record(doc_ref, data)
            if curr_status in (JobStatus.FAILED.value, JobStatus.TIMED_OUT.value):
                return False, "already_terminal", self._snapshot_to_record(doc_ref, data)

            now = time.time()
            curr_expires = float(data.get("lease_expires_at", 0.0) or 0.0)
            curr_attempt = data.get("attempt_id")

            if curr_status == JobStatus.RUNNING.value and now < curr_expires and curr_attempt != attempt_id:
                return False, "concurrent_active", self._snapshot_to_record(doc_ref, data)

            # Safety check: if lease expired after provider execution (e.g. Gemini) commenced,
            # NEVER automatically restart to prevent duplicate paid provider invocations.
            if curr_status == JobStatus.RUNNING.value and now >= curr_expires and data.get("provider_execution_started", False):
                err_msg = (
                    "Ambiguous worker termination after provider execution started. "
                    "Automatic restart prevented to avoid duplicate provider calls; manual recovery required."
                )
                completed_at = _utc_now_iso()
                fail_fields = {
                    "status": JobStatus.FAILED.value,
                    "stage": PipelineStage.FAILED.value,
                    "error_message": err_msg,
                    "error_status_code": 500,
                    "completed_at": completed_at,
                    "progress_message": "Execution aborted: lease expired after provider invocation started.",
                }
                transaction.update(doc_ref, fail_fields)
                updated_data = {**data, **fail_fields}
                return False, "ambiguous_failure", self._snapshot_to_record(doc_ref, updated_data)

            new_token = int(data.get("fencing_token", 0) or 0) + 1
            new_expires = now + lease_seconds
            started_at = data.get("started_at") or _utc_now_iso()

            update_fields = {
                "status": JobStatus.RUNNING.value,
                "stage": PipelineStage.STAGE1_DECISION_FRAMER.value,
                "attempt_id": attempt_id,
                "fencing_token": new_token,
                "lease_expires_at": new_expires,
                "started_at": started_at,
                "progress_message": "Execution started via worker.",
            }
            transaction.update(doc_ref, update_fields)
            updated_data = {**data, **update_fields}
            return True, "acquired", self._snapshot_to_record(doc_ref, updated_data)

        transaction = self._db.transaction()
        return _txn_claim(transaction)

    def mark_provider_execution_started(
        self,
        job_id: str,
        attempt_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
    ) -> bool:
        """Atomically verifies active attempt, fencing token, RUNNING status, and unexpired lease in Firestore before committing marker."""
        doc_ref = self._jobs_col.document(job_id)

        @firestore.transactional
        def _txn_mark(transaction: Any) -> bool:
            snapshot = doc_ref.get(transaction=transaction)
            if not snapshot.exists:
                logger.warning("mark_provider_execution_started: job %s not found in Firestore", job_id)
                return False

            data = snapshot.to_dict()
            status_val = data.get("status")
            curr_attempt = data.get("attempt_id")
            curr_token = int(data.get("fencing_token", 0) or 0)
            curr_expires = float(data.get("lease_expires_at", 0.0) or 0.0)
            now = time.time()

            # 1. Verify RUNNING status
            if status_val != JobStatus.RUNNING.value:
                logger.warning(
                    "mark_provider_execution_started rejected in Firestore for job %s: status '%s' is not RUNNING",
                    job_id,
                    status_val,
                )
                return False

            # 2. Verify attempt_id matches active claim if specified
            if attempt_id is not None and curr_attempt != attempt_id:
                logger.warning(
                    "mark_provider_execution_started rejected in Firestore for job %s: attempt '%s' != active '%s'",
                    job_id,
                    attempt_id,
                    curr_attempt,
                )
                return False

            # 3. Verify fencing_token matches active claim if specified
            if fencing_token is not None and curr_token != fencing_token:
                logger.warning(
                    "mark_provider_execution_started rejected in Firestore for job %s: fencing token %d != active %d",
                    job_id,
                    fencing_token,
                    curr_token,
                )
                return False

            # 4. Verify lease is not expired if lease was established
            if curr_expires > 0.0 and now >= curr_expires:
                logger.warning(
                    "mark_provider_execution_started rejected in Firestore for job %s: lease expired (now=%.2f, expires=%.2f)",
                    job_id,
                    now,
                    curr_expires,
                )
                return False

            transaction.update(doc_ref, {"provider_execution_started": True})
            return True

        transaction = self._db.transaction()
        return _txn_mark(transaction)

    def record_dispatch_status(
        self,
        job_id: str,
        dispatch_status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Records the outcome of Cloud Tasks task dispatch in Firestore."""
        doc_ref = self._jobs_col.document(job_id)
        update_fields: Dict[str, Any] = {
            "dispatch_status": dispatch_status,
            "dispatch_error": error_message,
        }
        if dispatch_status == "enqueue_failed":
            update_fields.update({
                "status": JobStatus.FAILED.value,
                "error_message": error_message,
                "error_status_code": 500,
                "completed_at": _utc_now_iso(),
                "progress_message": f"Dispatch failed: {error_message}",
            })
        elif dispatch_status == "dispatch_uncertain":
            # Do NOT mark terminal! Preserve QUEUED status so job can be safely reconciled.
            update_fields.update({
                "progress_message": "Task dispatch status uncertain; reconciliation required.",
            })
        doc_ref.update(update_fields)

    def recover_stale_jobs_on_startup(self) -> int:
        """Startup hook for Cloud Run / Firestore environments.

        Unlike SQLite (where a process restart implies local worker threads died),
        Cloud Run instances scale independently and share Firestore. Unconditionally
        failing active cloud jobs on instance startup would corrupt tasks executing
        on sibling instances or Cloud Tasks.

        Returns 0 to ensure non-destructive startup. Distributed job reconciliation
        is safely deferred to Cloud Tasks expiration and lease TTLs.
        """
        logger.info("FirestoreJobStorage: Startup check complete. Active jobs preserved for distributed execution.")
        return 0

    def list_jobs(
        self,
        owner_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[JobRecord]:
        """Lists recent jobs, optionally filtered by owner and ordered by created_at descending."""
        query = self._jobs_col
        if owner_id:
            query = query.where(filter=FieldFilter("owner_id", "==", owner_id))
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)

        snapshots = list(query.stream())
        return [self._snapshot_to_record(s.reference, s.to_dict()) for s in snapshots]

    def close(self) -> None:
        """Closes the underlying Firestore client session."""
        try:
            self._db.close()
        except Exception:
            pass

    def _snapshot_to_record(self, doc_ref: Any, data: Dict[str, Any]) -> JobRecord:
        """Deserializes a Firestore document snapshot into a validated JobRecord."""
        req_json = self._load_chunkable_payload(doc_ref, data, "request_json")
        req_dict = json.loads(req_json or "{}")
        request = AnalysisJobCreateRequest.model_validate(req_dict)

        response = None
        resp_json = self._load_chunkable_payload(doc_ref, data, "response_json")
        if resp_json:
            resp_dict = json.loads(resp_json)
            response = AnalysisResponse.model_validate(resp_dict)

        return JobRecord(
            job_id=data["job_id"],
            status=JobStatus(data["status"]),
            stage=PipelineStage(data["stage"]),
            request=request,
            response=response,
            error_message=data.get("error_message"),
            error_status_code=data.get("error_status_code"),
            owner_id=data.get("owner_id"),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            timeout_seconds=float(data.get("timeout_seconds", 180.0)),
            framer_timeout_seconds=data.get("framer_timeout_seconds"),
            boardroom_timeout_seconds=data.get("boardroom_timeout_seconds"),
            recommendation_timeout_seconds=data.get("recommendation_timeout_seconds"),
            scenario_timeout_seconds=data.get("scenario_timeout_seconds"),
            progress_message=data.get("progress_message", ""),
            attempt_id=data.get("attempt_id"),
            lease_expires_at=data.get("lease_expires_at"),
            fencing_token=int(data.get("fencing_token", 0) or 0),
            dispatch_status=data.get("dispatch_status", "pending"),
            dispatch_error=data.get("dispatch_error"),
            provider_execution_started=bool(data.get("provider_execution_started", False)),
        )

    # -------------------------------------------------------------------------
    # What-if Simulations
    # -------------------------------------------------------------------------

    def save_simulation(
        self,
        simulation_id: str,
        job_id: str,
        analysis_id: str,
        baseline_fingerprint: str,
        request_json: str,
        result_json: str,
        created_at: Optional[str] = None,
    ) -> None:
        """Persists a what-if simulation run idempotently."""
        cat = created_at or _utc_now_iso()
        doc_ref = self._simulations_col.document(simulation_id)
        base_data = {
            "simulation_id": simulation_id,
            "job_id": job_id,
            "analysis_id": analysis_id,
            "baseline_fingerprint": baseline_fingerprint,
            "request_json": request_json,
            "created_at": cat,
        }
        self._store_chunkable_payload(doc_ref, "result_json", result_json, base_data)

    def get_simulation(
        self,
        simulation_id: str,
        job_id_or_analysis_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted simulation by ID, optionally verifying parent job/analysis association."""
        doc_ref = self._simulations_col.document(simulation_id)
        snap = doc_ref.get()
        if not snap.exists:
            return None

        data = snap.to_dict()
        if job_id_or_analysis_id:
            if data.get("job_id") != job_id_or_analysis_id and data.get("analysis_id") != job_id_or_analysis_id:
                return None

        data["result_json"] = self._load_chunkable_payload(doc_ref, data, "result_json")
        return data

    def list_simulations(
        self,
        job_id_or_analysis_id: str,
    ) -> List[Dict[str, Any]]:
        """Lists all persisted simulations for a job or analysis ordered by creation date descending."""
        q_analysis = (
            self._simulations_col.where(filter=FieldFilter("analysis_id", "==", job_id_or_analysis_id))
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )
        snaps_analysis = list(q_analysis.stream())

        q_job = (
            self._simulations_col.where(filter=FieldFilter("job_id", "==", job_id_or_analysis_id))
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )
        snaps_job = list(q_job.stream())

        seen_sim_ids = set()
        results: List[Dict[str, Any]] = []
        for s in snaps_analysis + snaps_job:
            if s.id not in seen_sim_ids:
                seen_sim_ids.add(s.id)
                d = s.to_dict()
                d["result_json"] = self._load_chunkable_payload(s.reference, d, "result_json")
                results.append(d)

        # Ensure sorted by created_at DESC matching SQLite
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return results

    # -------------------------------------------------------------------------
    # What-if Simulation AI Explanations
    # -------------------------------------------------------------------------

    def save_simulation_explanation(
        self,
        simulation_id: str,
        analysis_id: str,
        baseline_fingerprint: str,
        prompt_version: str,
        model_name: str,
        explanation_json: str,
        created_at: Optional[str] = None,
    ) -> None:
        """Persists a what-if simulation AI explanation idempotently."""
        cat = created_at or _utc_now_iso()
        doc_ref = self._simulation_explanations_col.document(simulation_id)
        base_data = {
            "simulation_id": simulation_id,
            "analysis_id": analysis_id,
            "baseline_fingerprint": baseline_fingerprint,
            "prompt_version": prompt_version,
            "model_name": model_name,
            "created_at": cat,
        }
        self._store_chunkable_payload(doc_ref, "explanation_json", explanation_json, base_data)

    def get_simulation_explanation(
        self,
        simulation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted simulation AI explanation by simulation ID."""
        doc_ref = self._simulation_explanations_col.document(simulation_id)
        snap = doc_ref.get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        data["explanation_json"] = self._load_chunkable_payload(doc_ref, data, "explanation_json")
        return data

    # -------------------------------------------------------------------------
    # Action Intelligence Plans
    # -------------------------------------------------------------------------

    def save_action_plan(
        self,
        plan_id: str,
        analysis_id: str,
        source_recommendation_fingerprint: str,
        schema_version: str,
        generator_version: str,
        plan_json: str,
        owner_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Persists or replaces an IntelligentActionPlan idempotently."""
        cat = created_at or _utc_now_iso()
        doc_ref = self._action_plans_col.document(plan_id)
        base_data = {
            "plan_id": plan_id,
            "analysis_id": analysis_id,
            "source_recommendation_fingerprint": source_recommendation_fingerprint,
            "schema_version": schema_version,
            "generator_version": generator_version,
            "owner_id": owner_id,
            "created_at": cat,
        }
        self._store_chunkable_payload(doc_ref, "plan_json", plan_json, base_data)

    def get_action_plan(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the latest persisted action plan for an analysis, respecting owner_id scoping."""
        if owner_id:
            q_owner = (
                self._action_plans_col.where(filter=FieldFilter("analysis_id", "==", analysis_id))
                .where(filter=FieldFilter("owner_id", "==", owner_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            q_unowned = (
                self._action_plans_col.where(filter=FieldFilter("analysis_id", "==", analysis_id))
                .where(filter=FieldFilter("owner_id", "==", None))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            candidates = list(q_owner.stream()) + list(q_unowned.stream())
            if not candidates:
                return None
            candidates.sort(key=lambda s: s.to_dict().get("created_at", ""), reverse=True)
            snaps = [candidates[0]]
        else:
            query = (
                self._action_plans_col.where(filter=FieldFilter("analysis_id", "==", analysis_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            snaps = list(query.stream())

        if not snaps:
            return None

        doc_ref = snaps[0].reference
        data = snaps[0].to_dict()
        data["plan_json"] = self._load_chunkable_payload(doc_ref, data, "plan_json")
        return data

    def get_action_plan_by_id(
        self,
        plan_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted action plan by its unique plan_id."""
        doc_ref = self._action_plans_col.document(plan_id)
        snap = doc_ref.get()
        if not snap.exists:
            return None

        data = snap.to_dict()
        if owner_id and data.get("owner_id") is not None and data.get("owner_id") != owner_id:
            return None

        data["plan_json"] = self._load_chunkable_payload(doc_ref, data, "plan_json")
        return data

    def delete_action_plan(
        self,
        analysis_id: str,
    ) -> None:
        """Deletes all action plans associated with an analysis."""
        query = self._action_plans_col.where(filter=FieldFilter("analysis_id", "==", analysis_id))
        snaps = list(query.stream())
        for s in snaps:
            s.reference.delete()

    # -------------------------------------------------------------------------
    # Action Plan Claims (Durable Distributed Concurrency Control)
    # -------------------------------------------------------------------------

    def acquire_action_plan_claim(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
        ttl_seconds: float = 90.0,
    ) -> Tuple[bool, str, str]:
        """Attempts to acquire a durable generation claim for analysis_id in Firestore using atomic transactions.

        Returns:
            Tuple of (acquired: bool, status: str, claim_id: str).
            If acquired is False, another worker holds an active unexpired claim ('running').
        """
        now = time.time()
        new_claim_id = str(uuid.uuid4())
        claimed_at = _utc_now_iso()
        expires_at = now + ttl_seconds
        doc_ref = self._action_plan_claims_col.document(analysis_id)

        @firestore.transactional
        def _txn_acquire(transaction: Any) -> Tuple[bool, str, str]:
            snapshot = doc_ref.get(transaction=transaction)
            if snapshot.exists:
                data = snapshot.to_dict()
                curr_status = data.get("status")
                curr_expires = float(data.get("expires_at", 0.0))

                if curr_status == "running" and now < curr_expires:
                    # Active unexpired claim held by another process/worker
                    return False, "running", str(data.get("claim_id", ""))

                # Overwrite expired, failed, or ready claim atomically
                transaction.set(doc_ref, {
                    "analysis_id": analysis_id,
                    "claim_id": new_claim_id,
                    "status": "running",
                    "claimed_at": claimed_at,
                    "expires_at": expires_at,
                    "owner_id": owner_id,
                    "error_message": None,
                })
                return True, "acquired", new_claim_id
            else:
                transaction.set(doc_ref, {
                    "analysis_id": analysis_id,
                    "claim_id": new_claim_id,
                    "status": "running",
                    "claimed_at": claimed_at,
                    "expires_at": expires_at,
                    "owner_id": owner_id,
                    "error_message": None,
                })
                return True, "acquired", new_claim_id

        transaction = self._db.transaction()
        return _txn_acquire(transaction)

    def release_action_plan_claim(
        self,
        analysis_id: str,
        claim_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Transitions an action plan generation claim to 'ready' or 'failed'."""
        new_status = "ready" if success else "failed"
        doc_ref = self._action_plan_claims_col.document(analysis_id)

        @firestore.transactional
        def _txn_release(transaction: Any) -> None:
            snapshot = doc_ref.get(transaction=transaction)
            if not snapshot.exists:
                return
            data = snapshot.to_dict()
            if data.get("claim_id") != claim_id:
                # Do not overwrite if claim was superseded or reclaimed
                return

            transaction.update(doc_ref, {
                "status": new_status,
                "error_message": error_message,
            })

        transaction = self._db.transaction()
        _txn_release(transaction)

    def get_action_plan_claim(
        self,
        analysis_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves current generation claim state for analysis_id."""
        doc_ref = self._action_plan_claims_col.document(analysis_id)
        snap = doc_ref.get()
        if not snap.exists:
            return None
        return snap.to_dict()
