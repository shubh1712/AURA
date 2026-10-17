"""AURA Job Storage Interface.

Defines the abstract storage protocol and data transfer records for analysis jobs,
what-if simulations, and action intelligence plans.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from app.schemas.analysis import AnalysisResponse
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage


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
    boardroom_timeout_seconds: Optional[float]
    recommendation_timeout_seconds: Optional[float]
    scenario_timeout_seconds: Optional[float] = None
    progress_message: str = ""
    attempt_id: Optional[str] = None
    lease_expires_at: Optional[float] = None
    fencing_token: int = 0
    dispatch_status: str = "pending"
    dispatch_error: Optional[str] = None
    provider_execution_started: bool = False


@runtime_checkable
class JobStorageInterface(Protocol):
    """Abstract protocol defining the contract for AURA job storage backends."""

    def create_job(
        self,
        request: AnalysisJobCreateRequest,
        job_id: Optional[str] = None,
        default_timeout_seconds: float = 180.0,
    ) -> JobRecord:
        """Persists a new job in QUEUED status."""
        ...

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieves a job by its unique identifier."""
        ...

    def get_job_by_any_id(self, id_str: str) -> Optional[JobRecord]:
        """Resolves a JobRecord by either job_id directly or by internal analysis_id."""
        ...

    def update_running(
        self,
        job_id: str,
        stage: PipelineStage = PipelineStage.STAGE1_DECISION_FRAMER,
        message: str = "Execution started.",
    ) -> None:
        """Transitions job to RUNNING status with start timestamp."""
        ...

    def update_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        message: str,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Updates pipeline stage and progress message while job remains RUNNING."""
        ...

    def complete_job(
        self,
        job_id: str,
        response: AnalysisResponse,
        message: str = "Analysis completed successfully.",
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to SUCCEEDED status with full validated response payload."""
        ...

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_status_code: int = 500,
        stage: PipelineStage = PipelineStage.FAILED,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to FAILED status with error details."""
        ...

    def timeout_job(
        self,
        job_id: str,
        error_message: str = "Decision analysis timed out while evaluating the inquiry.",
        stage: PipelineStage = PipelineStage.TIMED_OUT,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Transitions job to TIMED_OUT status."""
        ...

    def acquire_job_execution_claim(
        self,
        job_id: str,
        attempt_id: str,
        lease_seconds: float = 300.0,
    ) -> Tuple[bool, str, Optional[JobRecord]]:
        """Atomically acquires an execution claim for a job with fencing token.

        Returns:
            Tuple of (acquired: bool, status: str, job: Optional[JobRecord]).
            status may be:
              - 'acquired': Worker successfully claimed the job.
              - 'already_completed': Job is already completed.
              - 'already_terminal': Job is already failed or timed out.
              - 'concurrent_active': Job is actively being processed under an unexpired lease.
              - 'ambiguous_failure': Job lease expired after provider execution started; manual recovery required.
              - 'not_found': Job does not exist.
        """
        ...

    def record_dispatch_status(
        self,
        job_id: str,
        dispatch_status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Records the outcome of Cloud Tasks task dispatch."""
        ...

    def mark_provider_execution_started(
        self,
        job_id: str,
        attempt_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
    ) -> bool:
        """Commits a durable marker indicating provider execution (e.g. Gemini) has commenced.

        Atomically verifies that the active attempt_id, fencing_token, RUNNING status,
        and unexpired lease are valid before committing the marker. Returns True if
        successfully committed, or False if the claim is stale, superseded, or expired.
        """
        ...

    def recover_stale_jobs_on_startup(self) -> int:
        """Recovers any jobs left in QUEUED or RUNNING states when the application starts."""
        ...

    def list_jobs(
        self,
        owner_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[JobRecord]:
        """Lists recent jobs, optionally filtered by owner."""
        ...

    def close(self) -> None:
        """Closes the underlying storage connection or client session."""
        ...

    # What-if simulations
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
        ...

    def get_simulation(
        self,
        simulation_id: str,
        job_id_or_analysis_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted simulation by ID, optionally verifying parent job/analysis association."""
        ...

    def list_simulations(
        self,
        job_id_or_analysis_id: str,
    ) -> List[Dict[str, Any]]:
        """Lists all persisted simulations for a job or analysis ordered by creation date descending."""
        ...

    # What-if simulation AI explanations
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
        ...

    def get_simulation_explanation(
        self,
        simulation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted simulation AI explanation by simulation ID."""
        ...

    # Action Intelligence
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
        ...

    def get_action_plan(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the latest persisted action plan for an analysis, respecting owner_id scoping."""
        ...

    def get_action_plan_by_id(
        self,
        plan_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted action plan by its unique plan_id."""
        ...

    def delete_action_plan(
        self,
        analysis_id: str,
    ) -> None:
        """Deletes action plans associated with an analysis."""
        ...

    def acquire_action_plan_claim(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
        ttl_seconds: float = 90.0,
    ) -> Tuple[bool, str, str]:
        """Attempts to acquire a durable generation claim for analysis_id."""
        ...

    def release_action_plan_claim(
        self,
        analysis_id: str,
        claim_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Transitions an action plan generation claim to 'ready' or 'failed'."""
        ...

    def get_action_plan_claim(
        self,
        analysis_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves current generation claim state for analysis_id."""
        ...
