"""AURA Storage Factory.

Instantiates and configures the appropriate JobStorageInterface implementation
based on application configuration.
"""

from typing import Optional
from app.config import settings
from app.services.jobs.base import JobStorageInterface
from app.services.jobs.storage import SQLiteJobStorage


def get_job_storage(
    backend: Optional[str] = None,
    db_path: Optional[str] = None,
) -> JobStorageInterface:
    """Returns a configured storage instance conforming to JobStorageInterface.

    Args:
        backend: Optional storage backend name (defaults to settings.AURA_STORAGE_BACKEND).
        db_path: Optional SQLite database file path (defaults to settings.AURA_JOBS_DB_PATH).

    Returns:
        JobStorageInterface implementation (SQLiteJobStorage).

    Raises:
        NotImplementedError: If firestore backend is selected prior to Phase 2 implementation.
        ValueError: If an unsupported storage backend is specified.
    """
    raw_backend = backend or settings.AURA_STORAGE_BACKEND
    selected_backend = raw_backend.strip().lower()

    if selected_backend == "sqlite":
        path = db_path or getattr(settings, "AURA_JOBS_DB_PATH", "aura_jobs.db")
        return SQLiteJobStorage(db_path=path)

    if selected_backend == "firestore":
        from app.services.jobs.firestore_storage import FirestoreJobStorage
        return FirestoreJobStorage()

    raise ValueError(
        f"Unsupported storage backend '{raw_backend}'. Supported backends: 'sqlite', 'firestore'."
    )
