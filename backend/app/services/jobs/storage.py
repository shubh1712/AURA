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
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage
from app.services.jobs.base import JobRecord, JobStorageInterface

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class SQLiteJobStorage(JobStorageInterface):
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
                    boardroom_timeout_seconds REAL,
                    recommendation_timeout_seconds REAL,
                    scenario_timeout_seconds REAL,
                    progress_message TEXT NOT NULL
                );
            """)
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN boardroom_timeout_seconds REAL;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN recommendation_timeout_seconds REAL;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN scenario_timeout_seconds REAL;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN attempt_id TEXT;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN lease_expires_at REAL;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN fencing_token INTEGER DEFAULT 0;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN dispatch_status TEXT DEFAULT 'pending';")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN dispatch_error TEXT;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE analysis_jobs ADD COLUMN provider_execution_started INTEGER DEFAULT 0;")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_owner ON analysis_jobs(owner_id);
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
            """)
            # What-if simulation persistence table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS what_if_simulations (
                    simulation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    baseline_fingerprint TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_simulations_job ON what_if_simulations(job_id);
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_simulations_analysis ON what_if_simulations(analysis_id);
            """)
            # What-if simulation AI explanation persistence table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS what_if_simulation_explanations (
                    simulation_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    baseline_fingerprint TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    explanation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sim_exp_analysis ON what_if_simulation_explanations(analysis_id);
            """)
            # Action Intelligence plan persistence table (Day 8A)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS action_plans (
                    plan_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    source_recommendation_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    generator_version TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    owner_id TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_action_plans_analysis ON action_plans(analysis_id);
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_action_plans_fingerprint ON action_plans(source_recommendation_fingerprint);
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_action_plans_owner ON action_plans(owner_id);
            """)
            # Action Intelligence generation claims (Day 8B durable concurrency control)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS action_plan_claims (
                    analysis_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    owner_id TEXT,
                    error_message TEXT
                );
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claims_status ON action_plan_claims(status);
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
        boardroom_sec = request.boardroom_operation_timeout_seconds
        recommendation_sec = request.recommendation_operation_timeout_seconds
        scenario_sec = request.scenario_operation_timeout_seconds
        initial_msg = "Job submitted and queued for execution."

        req_json = request.model_dump_json()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id, status, stage, request_json, response_json,
                    error_message, error_status_code, owner_id,
                    created_at, started_at, completed_at,
                    timeout_seconds, framer_timeout_seconds, boardroom_timeout_seconds,
                    recommendation_timeout_seconds, scenario_timeout_seconds, progress_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    boardroom_sec,
                    recommendation_sec,
                    scenario_sec,
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
            boardroom_timeout_seconds=boardroom_sec,
            recommendation_timeout_seconds=recommendation_sec,
            scenario_timeout_seconds=scenario_sec,
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
        fencing_token: Optional[int] = None,
    ) -> None:
        """Updates pipeline stage and progress message while job remains RUNNING."""
        with self._lock:
            if fencing_token is not None:
                cur = self._conn.execute(
                    "SELECT fencing_token FROM analysis_jobs WHERE job_id = ?;", (job_id,)
                )
                row = cur.fetchone()
                if row and row["fencing_token"] is not None and row["fencing_token"] != fencing_token:
                    logger.warning(
                        "Fenced update_stage rejected for job %s: current token %s != caller %s",
                        job_id,
                        row["fencing_token"],
                        fencing_token,
                    )
                    return

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
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to SUCCEEDED status with full validated response payload."""
        completed_at = _utc_now_iso()
        resp_json = response.model_dump_json()
        with self._lock:
            if fencing_token is not None:
                cur = self._conn.execute(
                    "SELECT fencing_token FROM analysis_jobs WHERE job_id = ?;", (job_id,)
                )
                row = cur.fetchone()
                if row and row["fencing_token"] is not None and row["fencing_token"] != fencing_token:
                    logger.warning(
                        "Fenced complete_job rejected for job %s: current token %s != caller %s",
                        job_id,
                        row["fencing_token"],
                        fencing_token,
                    )
                    return

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
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to FAILED status with error details."""
        completed_at = _utc_now_iso()
        with self._lock:
            if fencing_token is not None:
                cur = self._conn.execute(
                    "SELECT fencing_token FROM analysis_jobs WHERE job_id = ?;", (job_id,)
                )
                row = cur.fetchone()
                if row and row["fencing_token"] is not None and row["fencing_token"] != fencing_token:
                    logger.warning(
                        "Fenced fail_job rejected for job %s: current token %s != caller %s",
                        job_id,
                        row["fencing_token"],
                        fencing_token,
                    )
                    return

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
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to TIMED_OUT status."""
        completed_at = _utc_now_iso()
        with self._lock:
            if fencing_token is not None:
                cur = self._conn.execute(
                    "SELECT fencing_token FROM analysis_jobs WHERE job_id = ?;", (job_id,)
                )
                row = cur.fetchone()
                if row and row["fencing_token"] is not None and row["fencing_token"] != fencing_token:
                    logger.warning(
                        "Fenced timeout_job rejected for job %s: current token %s != caller %s",
                        job_id,
                        row["fencing_token"],
                        fencing_token,
                    )
                    return

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

    def acquire_job_execution_claim(
        self,
        job_id: str,
        attempt_id: str,
        lease_seconds: float = 300.0,
    ) -> Tuple[bool, str, Optional[JobRecord]]:
        """Atomically acquires an execution claim for a job with fencing token in SQLite."""
        now = time.time()
        with self._lock:
            cur = self._conn.execute("SELECT * FROM analysis_jobs WHERE job_id = ?;", (job_id,))
            row = cur.fetchone()
            if not row:
                return False, "not_found", None

            rec = self._row_to_record(row)
            if rec.status == JobStatus.SUCCEEDED:
                return False, "already_completed", rec
            if rec.status in (JobStatus.FAILED, JobStatus.TIMED_OUT):
                return False, "already_terminal", rec

            curr_expires = float(rec.lease_expires_at or 0.0)
            if rec.status == JobStatus.RUNNING and now < curr_expires and rec.attempt_id != attempt_id:
                return False, "concurrent_active", rec

            # Safety check: if lease expired after provider execution (e.g. Gemini) commenced,
            # NEVER automatically restart to prevent duplicate paid provider invocations.
            if rec.status == JobStatus.RUNNING and now >= curr_expires and rec.provider_execution_started:
                err_msg = (
                    "Ambiguous worker termination after provider execution started. "
                    "Automatic restart prevented to avoid duplicate provider calls; manual recovery required."
                )
                completed_at = _utc_now_iso()
                self._conn.execute(
                    """
                    UPDATE analysis_jobs
                    SET status = ?, stage = ?, error_message = ?, error_status_code = 500,
                        completed_at = ?, progress_message = ?
                    WHERE job_id = ?;
                    """,
                    (
                        JobStatus.FAILED.value,
                        PipelineStage.FAILED.value,
                        err_msg,
                        completed_at,
                        "Execution aborted: lease expired after provider invocation started.",
                        job_id,
                    ),
                )
                self._conn.commit()
                cur2 = self._conn.execute("SELECT * FROM analysis_jobs WHERE job_id = ?;", (job_id,))
                updated_row = cur2.fetchone()
                return False, "ambiguous_failure", self._row_to_record(updated_row)

            new_token = (rec.fencing_token or 0) + 1
            new_expires = now + lease_seconds
            started_at = rec.started_at or _utc_now_iso()

            self._conn.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, stage = ?, attempt_id = ?, lease_expires_at = ?,
                    fencing_token = ?, started_at = ?, progress_message = ?
                WHERE job_id = ?;
                """,
                (
                    JobStatus.RUNNING.value,
                    PipelineStage.STAGE1_DECISION_FRAMER.value,
                    attempt_id,
                    new_expires,
                    new_token,
                    started_at,
                    "Execution started via worker.",
                    job_id,
                ),
            )
            self._conn.commit()

            cur2 = self._conn.execute("SELECT * FROM analysis_jobs WHERE job_id = ?;", (job_id,))
            updated_row = cur2.fetchone()
            return True, "acquired", self._row_to_record(updated_row)

    def mark_provider_execution_started(
        self,
        job_id: str,
        attempt_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
    ) -> bool:
        """Atomically verifies active attempt, fencing token, RUNNING status, and unexpired lease before committing marker."""
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "SELECT status, attempt_id, fencing_token, lease_expires_at, provider_execution_started FROM analysis_jobs WHERE job_id = ?;",
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                logger.warning("mark_provider_execution_started: job %s not found", job_id)
                return False

            status_val = row["status"]
            curr_attempt = row["attempt_id"] if "attempt_id" in row.keys() else None
            curr_token = row["fencing_token"] if "fencing_token" in row.keys() and row["fencing_token"] is not None else 0
            curr_expires = float(row["lease_expires_at"]) if "lease_expires_at" in row.keys() and row["lease_expires_at"] is not None else None

            # 1. Verify RUNNING status
            if status_val != JobStatus.RUNNING.value:
                logger.warning(
                    "mark_provider_execution_started rejected for job %s: status '%s' is not RUNNING",
                    job_id,
                    status_val,
                )
                return False

            # 2. Verify attempt_id matches active claim if specified
            if attempt_id is not None and curr_attempt != attempt_id:
                logger.warning(
                    "mark_provider_execution_started rejected for job %s: attempt '%s' != active '%s'",
                    job_id,
                    attempt_id,
                    curr_attempt,
                )
                return False

            # 3. Verify fencing_token matches active claim if specified
            if fencing_token is not None and curr_token != fencing_token:
                logger.warning(
                    "mark_provider_execution_started rejected for job %s: fencing token %d != active %d",
                    job_id,
                    fencing_token,
                    curr_token,
                )
                return False

            # 4. Verify lease is not expired if lease was established
            if curr_expires is not None and now >= curr_expires:
                logger.warning(
                    "mark_provider_execution_started rejected for job %s: lease expired (now=%.2f, expires=%.2f)",
                    job_id,
                    now,
                    curr_expires,
                )
                return False

            self._conn.execute(
                "UPDATE analysis_jobs SET provider_execution_started = 1 WHERE job_id = ?;",
                (job_id,),
            )
            self._conn.commit()
            return True

    def record_dispatch_status(
        self,
        job_id: str,
        dispatch_status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Records the outcome of Cloud Tasks task dispatch in SQLite."""
        with self._lock:
            if dispatch_status == "enqueue_failed":
                self._conn.execute(
                    """
                    UPDATE analysis_jobs
                    SET dispatch_status = ?, dispatch_error = ?, status = ?,
                        error_message = ?, error_status_code = 500, completed_at = ?,
                        progress_message = ?
                    WHERE job_id = ?;
                    """,
                    (
                        dispatch_status,
                        error_message,
                        JobStatus.FAILED.value,
                        error_message,
                        _utc_now_iso(),
                        f"Dispatch failed: {error_message}",
                        job_id,
                    ),
                )
            elif dispatch_status == "dispatch_uncertain":
                # Do NOT mark terminal! Preserve QUEUED status so job can be reconciled.
                self._conn.execute(
                    """
                    UPDATE analysis_jobs
                    SET dispatch_status = ?, dispatch_error = ?,
                        progress_message = ?
                    WHERE job_id = ?;
                    """,
                    (
                        dispatch_status,
                        error_message,
                        "Task dispatch status uncertain; reconciliation required.",
                        job_id,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE analysis_jobs
                    SET dispatch_status = ?, dispatch_error = ?
                    WHERE job_id = ?;
                    """,
                    (dispatch_status, error_message, job_id),
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
            boardroom_timeout_seconds=row["boardroom_timeout_seconds"] if "boardroom_timeout_seconds" in row.keys() else None,
            recommendation_timeout_seconds=row["recommendation_timeout_seconds"] if "recommendation_timeout_seconds" in row.keys() else None,
            scenario_timeout_seconds=row["scenario_timeout_seconds"] if "scenario_timeout_seconds" in row.keys() else None,
            progress_message=row["progress_message"],
            attempt_id=row["attempt_id"] if "attempt_id" in row.keys() else None,
            lease_expires_at=row["lease_expires_at"] if "lease_expires_at" in row.keys() else None,
            fencing_token=row["fencing_token"] if "fencing_token" in row.keys() and row["fencing_token"] is not None else 0,
            dispatch_status=row["dispatch_status"] if "dispatch_status" in row.keys() and row["dispatch_status"] is not None else "pending",
            dispatch_error=row["dispatch_error"] if "dispatch_error" in row.keys() else None,
            provider_execution_started=bool(row["provider_execution_started"]) if "provider_execution_started" in row.keys() and row["provider_execution_started"] is not None else False,
        )

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
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO what_if_simulations (
                    simulation_id, job_id, analysis_id, baseline_fingerprint,
                    request_json, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    simulation_id,
                    job_id,
                    analysis_id,
                    baseline_fingerprint,
                    request_json,
                    result_json,
                    cat,
                ),
            )
            self._conn.commit()

    def get_simulation(
        self,
        simulation_id: str,
        job_id_or_analysis_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted simulation by ID, optionally verifying parent job/analysis association."""
        with self._lock:
            if job_id_or_analysis_id:
                cur = self._conn.execute(
                    """
                    SELECT * FROM what_if_simulations
                    WHERE simulation_id = ? AND (job_id = ? OR analysis_id = ?);
                    """,
                    (simulation_id, job_id_or_analysis_id, job_id_or_analysis_id),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM what_if_simulations WHERE simulation_id = ?;",
                    (simulation_id,),
                )
            row = cur.fetchone()

        if not row:
            return None
        return dict(row)

    def list_simulations(
        self,
        job_id_or_analysis_id: str,
    ) -> List[Dict[str, Any]]:
        """Lists all persisted simulations for a job or analysis ordered by creation date descending."""
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM what_if_simulations
                WHERE job_id = ? OR analysis_id = ?
                ORDER BY created_at DESC;
                """,
                (job_id_or_analysis_id, job_id_or_analysis_id),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

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
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO what_if_simulation_explanations (
                    simulation_id, analysis_id, baseline_fingerprint,
                    prompt_version, model_name, explanation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    simulation_id,
                    analysis_id,
                    baseline_fingerprint,
                    prompt_version,
                    model_name,
                    explanation_json,
                    cat,
                ),
            )
            self._conn.commit()

    def get_simulation_explanation(
        self,
        simulation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted simulation AI explanation by simulation ID."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM what_if_simulation_explanations WHERE simulation_id = ?;",
                (simulation_id,),
            )
            row = cur.fetchone()

        if not row:
            return None
        return dict(row)

    def get_job_by_any_id(self, id_str: str) -> Optional[JobRecord]:
        """Resolves a JobRecord by either job_id directly or by internal analysis_id."""
        job = self.get_job(id_str)
        if job is not None:
            return job

        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM analysis_jobs WHERE response_json LIKE ?;",
                (f'%"{id_str}"%',),
            )
            rows = cur.fetchall()

        for row in rows:
            rec = self._row_to_record(row)
            if rec.response is not None and rec.response.analysis_id == id_str:
                return rec
        return None

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
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO action_plans (
                    plan_id, analysis_id, source_recommendation_fingerprint,
                    schema_version, generator_version, plan_json, owner_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    plan_id,
                    analysis_id,
                    source_recommendation_fingerprint,
                    schema_version,
                    generator_version,
                    plan_json,
                    owner_id,
                    cat,
                ),
            )
            self._conn.commit()

    def get_action_plan(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the latest persisted action plan for an analysis, respecting owner_id scoping."""
        with self._lock:
            if owner_id:
                cur = self._conn.execute(
                    """
                    SELECT * FROM action_plans
                    WHERE analysis_id = ? AND (owner_id IS NULL OR owner_id = ?)
                    ORDER BY created_at DESC LIMIT 1;
                    """,
                    (analysis_id, owner_id),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT * FROM action_plans
                    WHERE analysis_id = ?
                    ORDER BY created_at DESC LIMIT 1;
                    """,
                    (analysis_id,),
                )
            row = cur.fetchone()

        if not row:
            return None
        return dict(row)

    def get_action_plan_by_id(
        self,
        plan_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted action plan by its unique plan_id."""
        with self._lock:
            if owner_id:
                cur = self._conn.execute(
                    """
                    SELECT * FROM action_plans
                    WHERE plan_id = ? AND (owner_id IS NULL OR owner_id = ?);
                    """,
                    (plan_id, owner_id),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM action_plans WHERE plan_id = ?;",
                    (plan_id,),
                )
            row = cur.fetchone()

        if not row:
            return None
        return dict(row)

    def delete_action_plan(
        self,
        analysis_id: str,
    ) -> None:
        """Deletes action plans associated with an analysis."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM action_plans WHERE analysis_id = ?;",
                (analysis_id,),
            )
            self._conn.commit()

    def acquire_action_plan_claim(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
        ttl_seconds: float = 90.0,
    ) -> Tuple[bool, str, str]:
        """Attempts to acquire a durable generation claim for analysis_id in SQLite.

        Returns:
            Tuple of (acquired: bool, status: str, claim_id: str).
            If acquired is False, another worker/request holds an active unexpired claim ('running').
        """
        now = time.time()
        claim_id = str(uuid.uuid4())
        claimed_at = _utc_now_iso()
        expires_at = now + ttl_seconds

        with self._lock:
            cur = self._conn.execute(
                "SELECT claim_id, status, expires_at FROM action_plan_claims WHERE analysis_id = ?;",
                (analysis_id,),
            )
            row = cur.fetchone()
            if row:
                curr_status = row["status"]
                curr_expires = float(row["expires_at"])
                if curr_status == "running" and now < curr_expires:
                    # Active unexpired claim held by another process
                    return False, "running", str(row["claim_id"])

                # Previous claim is completed, failed, or expired. Overwrite atomically with new running claim.
                self._conn.execute(
                    """
                    UPDATE action_plan_claims
                    SET claim_id = ?, status = 'running', claimed_at = ?, expires_at = ?, owner_id = ?, error_message = NULL
                    WHERE analysis_id = ?;
                    """,
                    (claim_id, claimed_at, expires_at, owner_id, analysis_id),
                )
                self._conn.commit()
                return True, "acquired", claim_id
            else:
                self._conn.execute(
                    """
                    INSERT INTO action_plan_claims (
                        analysis_id, claim_id, status, claimed_at, expires_at, owner_id, error_message
                    ) VALUES (?, ?, 'running', ?, ?, ?, NULL);
                    """,
                    (analysis_id, claim_id, claimed_at, expires_at, owner_id),
                )
                self._conn.commit()
                return True, "acquired", claim_id

    def release_action_plan_claim(
        self,
        analysis_id: str,
        claim_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Transitions an action plan generation claim to 'ready' or 'failed'."""
        new_status = "ready" if success else "failed"
        with self._lock:
            self._conn.execute(
                """
                UPDATE action_plan_claims
                SET status = ?, error_message = ?
                WHERE analysis_id = ? AND claim_id = ?;
                """,
                (new_status, error_message, analysis_id, claim_id),
            )
            self._conn.commit()

    def get_action_plan_claim(
        self,
        analysis_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves current generation claim state for analysis_id."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM action_plan_claims WHERE analysis_id = ?;",
                (analysis_id,),
            )
            row = cur.fetchone()

        if not row:
            return None
        return dict(row)
