"""Offline tests for AURA Storage Factory and JobStorageInterface compatibility.

Verifies:
1. JobStorageInterface contract and SQLiteJobStorage conformance.
2. get_job_storage factory instantiation and default SQLite backend.
3. Explicit rejection of unsupported backends.
4. NotImplementedError for pending Firestore backend.
5. AnalysisJobManager dependency injection and factory integration.
"""

from typing import Any, Dict, List, Optional, Tuple
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage
from app.services.jobs.base import JobRecord, JobStorageInterface
from app.services.jobs.factory import get_job_storage
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage


class TestStorageInterfaceAndFactory:
    """Tests storage protocol conformance, factory resolution, and configuration validation."""

    def test_sqlite_storage_conforms_to_interface(self) -> None:
        """Verifies that SQLiteJobStorage implements JobStorageInterface."""
        storage = SQLiteJobStorage(db_path=":memory:")
        assert isinstance(storage, JobStorageInterface)
        storage.close()

    def test_factory_returns_sqlite_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies get_job_storage returns a valid SQLiteJobStorage when unset."""
        monkeypatch.delenv("AURA_STORAGE_BACKEND", raising=False)
        storage = get_job_storage(db_path=":memory:")
        assert isinstance(storage, JobStorageInterface)
        assert isinstance(storage, SQLiteJobStorage)
        assert storage.db_path == ":memory:"
        storage.close()

    def test_factory_explicit_sqlite_case_insensitive(self) -> None:
        """Verifies get_job_storage handles case-insensitive backend specification."""
        storage_lower = get_job_storage(backend="sqlite", db_path=":memory:")
        assert isinstance(storage_lower, SQLiteJobStorage)
        storage_lower.close()

        storage_upper = get_job_storage(backend="SQLITE", db_path=":memory:")
        assert isinstance(storage_upper, SQLiteJobStorage)
        storage_upper.close()

    def test_factory_firestore_selects_firestore_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies get_job_storage instantiates FirestoreJobStorage when backend is firestore."""
        from app.services.jobs.firestore_storage import FirestoreJobStorage

        mock_instantiated = False

        def mock_init(self: Any, *args: Any, **kwargs: Any) -> None:
            nonlocal mock_instantiated
            mock_instantiated = True

        monkeypatch.setattr(FirestoreJobStorage, "__init__", mock_init)
        storage = get_job_storage(backend="firestore")
        assert isinstance(storage, FirestoreJobStorage)
        assert mock_instantiated is True

    def test_factory_unsupported_backend_raises_value_error(self) -> None:
        """Verifies get_job_storage rejects unknown backends with ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_job_storage(backend="mongodb")
        assert "Unsupported storage backend" in str(exc_info.value)

    def test_settings_storage_backend_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies Pydantic settings validates and normalizes AURA_STORAGE_BACKEND."""
        # 1. Valid sqlite
        monkeypatch.setenv("AURA_STORAGE_BACKEND", "sqlite")
        assert Settings().AURA_STORAGE_BACKEND == "sqlite"

        # 2. Valid uppercase normalized to lower
        monkeypatch.setenv("AURA_STORAGE_BACKEND", " SQLITE ")
        assert Settings().AURA_STORAGE_BACKEND == "sqlite"

        # 3. Valid firestore
        monkeypatch.setenv("AURA_STORAGE_BACKEND", "firestore")
        assert Settings().AURA_STORAGE_BACKEND == "firestore"

        # 4. Invalid backend rejected
        monkeypatch.setenv("AURA_STORAGE_BACKEND", "postgres")
        with pytest.raises(ValidationError):
            Settings()

        # 5. Empty backend rejected
        monkeypatch.setenv("AURA_STORAGE_BACKEND", "")
        with pytest.raises(ValidationError):
            Settings()

    def test_manager_uses_factory_default_storage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies AnalysisJobManager initializes storage via factory when None is passed."""
        monkeypatch.setattr("app.config.settings.AURA_JOBS_DB_PATH", ":memory:")
        manager = AnalysisJobManager(storage=None)
        assert isinstance(manager.storage, JobStorageInterface)
        assert isinstance(manager.storage, SQLiteJobStorage)
        manager.shutdown(wait=False)

    def test_manager_preserves_custom_storage_injection(self) -> None:
        """Verifies AnalysisJobManager retains an injected JobStorageInterface instance."""
        custom_storage = SQLiteJobStorage(db_path=":memory:")
        manager = AnalysisJobManager(storage=custom_storage)
        assert manager.storage is custom_storage
        manager.shutdown(wait=False)
        custom_storage.close()

    def test_custom_mock_storage_conformance(self) -> None:
        """Verifies that an alternative mock implementation satisfying the protocol is accepted."""
        class DummyStorage:
            def create_job(self, request, job_id=None, default_timeout_seconds=180.0):
                return JobRecord(
                    job_id=job_id or "test-123",
                    status=JobStatus.QUEUED,
                    stage=PipelineStage.QUEUED,
                    request=request,
                    response=None,
                    error_message=None,
                    error_status_code=None,
                    owner_id=request.owner_id,
                    created_at="2026-10-16T00:00:00Z",
                    started_at=None,
                    completed_at=None,
                    timeout_seconds=default_timeout_seconds,
                    framer_timeout_seconds=None,
                    boardroom_timeout_seconds=None,
                    recommendation_timeout_seconds=None,
                    progress_message="",
                )
            def get_job(self, job_id): return None
            def get_job_by_any_id(self, id_str): return None
            def update_running(self, job_id, stage=PipelineStage.STAGE1_DECISION_FRAMER, message=""): pass
            def update_stage(self, job_id, stage, message, fencing_token=None): pass
            def complete_job(self, job_id, response, message="", fencing_token=None): pass
            def fail_job(self, job_id, error_message, error_status_code=500, stage=PipelineStage.FAILED, fencing_token=None): pass
            def timeout_job(self, job_id, error_message="", stage=PipelineStage.TIMED_OUT, fencing_token=None): pass
            def recover_stale_jobs_on_startup(self): return 0
            def list_jobs(self, owner_id=None, limit=50): return []
            def close(self): pass
            def save_simulation(self, simulation_id, job_id, analysis_id, baseline_fingerprint, request_json, result_json, created_at=None): pass
            def get_simulation(self, simulation_id, job_id_or_analysis_id=None): return None
            def list_simulations(self, job_id_or_analysis_id): return []
            def save_simulation_explanation(self, simulation_id, analysis_id, baseline_fingerprint, prompt_version, model_name, explanation_json, created_at=None): pass
            def get_simulation_explanation(self, simulation_id): return None
            def save_action_plan(self, plan_id, analysis_id, source_recommendation_fingerprint, schema_version, generator_version, plan_json, owner_id=None, created_at=None): pass
            def get_action_plan(self, analysis_id, owner_id=None): return None
            def get_action_plan_by_id(self, plan_id, owner_id=None): return None
            def delete_action_plan(self, analysis_id): pass
            def acquire_action_plan_claim(self, analysis_id, owner_id=None, ttl_seconds=90.0): return True, "acquired", "c1"
            def release_action_plan_claim(self, analysis_id, claim_id, success, error_message=None): pass
            def get_action_plan_claim(self, analysis_id): return None
            def acquire_job_execution_claim(self, job_id, attempt_id, lease_seconds=300.0): return True, "acquired", None
            def record_dispatch_status(self, job_id, dispatch_status, dispatch_error=None): pass
            def mark_provider_execution_started(self, job_id, attempt_id=None, fencing_token=None): return True

        dummy = DummyStorage()
        assert isinstance(dummy, JobStorageInterface)

        manager = AnalysisJobManager(storage=dummy)
        assert manager.storage is dummy
        manager.shutdown(wait=False)
