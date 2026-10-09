"""AURA SQLite Job Storage.

Provides restart-safe, ACID persistence for asynchronous analysis jobs using
Python's built-in sqlite3. Zero external dependencies required.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Optional
import uuid

from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    """In-memory representation of a persisted analysis job."""
    job_id: str
    status: JobStatus
    stage: PipelineStage
    request: AnalysisJobCreateRequest
    response: Optional[AnalysisResponse]
    error_message: Optional[str]
    error_status_code: Optional[int]
    owner_id: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    timeout_seconds: float
    framer_timeout_seconds: Optional[float]
    progress_message: str


class SQLiteJobStorage:
    """Thread-safe SQLite storage for analysis jobs."""

    def __init__(self, db_path: str = "aura_jobs.db") -> None:
        """Initializes storage and ensures the analysis_jobs table exists.

        Args:
            db_path: Path to the SQLite database file, or ':memory:' for tests.
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Creates the job table and indexes if not already present."""
        with self._lock:
            # Enable WAL mode for high concurrency when not in-memory
            if self.db_path != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode=WAL;")
                except sqlite3.Error:
                    pass

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT,
                    error_message TEXT,
                    error_status_code INTEGER,
                    owner_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    timeout_seconds REAL NOT NULL,
                    framer_timeout_seconds REAL,
                    progress_message TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_owner ON analysis_jobs(owner_id);
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
            """)
            self._conn.commit()

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
        framer_sec = request.framer_operation_timeout_seconds
        initial_msg = "Job submitted and queued for execution."

        req_json = request.model_dump_json()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id, status, stage, request_json, response_json,
                    error_message, error_status_code, owner_id,
                    created_at, started_at, completed_at,
                    timeout_seconds, framer_timeout_seconds, progress_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    jid,
                    JobStatus.QUEUED.value,
                    PipelineStage.QUEUED.value,
                    req_json,
                    None,
                    None,
                    None,
                    request.owner_id,
                    created_at,
                    None,
                    None,
                    timeout_sec,
                    framer_sec,
                    initial_msg,
                ),
            )
            self._conn.commit()

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
            timeout_seconds=timeout_sec,
            framer_timeout_seconds=framer_sec,
            progress_message=initial_msg,
        )

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieves a job by its unique identifier."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?;",
                (job_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return self._row_to_record(row)

    def update_running(
        self,
        job_id: str,
        stage: PipelineStage = PipelineStage.STAGE1_DECISION_FRAMER,
        message: str = "Execution started.",
    ) -> None:
        """Transitions job to RUNNING status with start timestamp."""
        started_at = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, stage = ?, started_at = ?, progress_message = ?
                WHERE job_id = ?;
                """,
                (
                    JobStatus.RUNNING.value,
                    stage.value,
                    started_at,
                    message,
                    job_id,
                ),
            )
            self._conn.commit()

    def update_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        message: str,
    ) -> None:
        """Updates pipeline stage and progress message while job remains RUNNING."""
        with self._lock:
            self._conn.execute(
                """
                UPDATE analysis_jobs
                SET stage = ?, progress_message = ?
                WHERE job_id = ? AND status = ?;
                """,
                (
                    stage.value,
                    message,
                    job_id,
                    JobStatus.RUNNING.value,
                ),
            )
            self._conn.commit()

    def complete_job(
        self,
        job_id: str,
        response: AnalysisResponse,
        message: str = "Analysis completed successfully.",
    ) -> None:
        """Transitions job to SUCCEEDED status with full validated response payload."""
        completed_at = _utc_now_iso()
        resp_json = response.model_dump_json()
        with self._lock:
            self._conn.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, stage = ?, response_json = ?, completed_at = ?, progress_message = ?
                WHERE job_id = ?;
                """,
                (
                    JobStatus.SUCCEEDED.value,
                    PipelineStage.COMPLETED.value,
                    resp_json,
                    completed_at,
                    message,
                    job_id,
                ),
            )
            self._conn.commit()

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_status_code: int = 500,
        stage: PipelineStage = PipelineStage.FAILED,
    ) -> None:
        """Transitions job to FAILED status with error details."""
        completed_at = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, stage = ?, error_message = ?, error_status_code = ?,
                    completed_at = ?, progress_message = ?
                WHERE job_id = ?;
                """,
                (
                    JobStatus.FAILED.value,
                    stage.value,
                    error_message,
                    error_status_code,
                    completed_at,
                    f"Job failed: {error_message}",
                    job_id,
                ),
            )
            self._conn.commit()

    def timeout_job(
        self,
        job_id: str,
        error_message: str = "Decision analysis timed out while evaluating the inquiry.",
        stage: PipelineStage = PipelineStage.TIMED_OUT,
    ) -> None:
        """Transitions job to TIMED_OUT status."""
        completed_at = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, stage = ?, error_message = ?, error_status_code = 504,
                    completed_at = ?, progress_message = ?
                WHERE job_id = ?;
                """,
                (
                    JobStatus.TIMED_OUT.value,
                    stage.value,
                    error_message,
                    completed_at,
                    f"Job timed out: {error_message}",
                    job_id,
                ),
            )
            self._conn.commit()

    def recover_stale_jobs_on_startup(self) -> int:
        """Recovers any jobs left in QUEUED or RUNNING states when the application starts.

        Guarantees restart safety: orphaned jobs from a previous process crash are marked
        FAILED with an explanatory message rather than hanging indefinitely.
        """
        completed_at = _utc_now_iso()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, stage = ?, error_message = ?, error_status_code = 500,
                    completed_at = ?, progress_message = ?
                WHERE status IN (?, ?);
                """,
                (
                    JobStatus.FAILED.value,
                    PipelineStage.FAILED.value,
                    "Job interrupted by process restart.",
                    completed_at,
                    "Job interrupted by server restart.",
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ),
            )
            self._conn.commit()
            recovered = cur.rowcount

        if recovered > 0:
            logger.info("Recovered %d stale jobs from prior process execution.", recovered)
        return recovered

    def list_jobs(
        self,
        owner_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[JobRecord]:
        """Lists recent jobs, optionally filtered by owner."""
        with self._lock:
            if owner_id:
                cur = self._conn.execute(
                    """
                    SELECT * FROM analysis_jobs
                    WHERE owner_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (owner_id, limit),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT * FROM analysis_jobs
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

        return [self._row_to_record(r) for r in rows]

    def close(self) -> None:
        """Closes the underlying database connection."""
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def _row_to_record(self, row: sqlite3.Row) -> JobRecord:
        """Deserializes a database row into a JobRecord."""
        req_data = json.loads(row["request_json"])
        request = AnalysisJobCreateRequest.model_validate(req_data)

        response = None
        if row["response_json"]:
            resp_data = json.loads(row["response_json"])
            response = AnalysisResponse.model_validate(resp_data)

        return JobRecord(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            stage=PipelineStage(row["stage"]),
            request=request,
            response=response,
            error_message=row["error_message"],
            error_status_code=row["error_status_code"],
            owner_id=row["owner_id"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            timeout_seconds=row["timeout_seconds"],
            framer_timeout_seconds=row["framer_timeout_seconds"],
            progress_message=row["progress_message"],
        )
