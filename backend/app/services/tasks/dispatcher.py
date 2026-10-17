"""AURA Cloud Tasks Dispatcher.

Enqueues asynchronous analysis jobs into Google Cloud Tasks for durable, authenticated
dispatch to Cloud Run internal worker endpoints.
"""

import json
import logging
import os
from typing import Any, Dict, Optional
import uuid

from google.api_core import exceptions as google_exceptions
from google.cloud import tasks_v2
from google.protobuf import duration_pb2

from app.config import Settings, settings
from app.services.jobs.base import JobStorageInterface

logger = logging.getLogger(__name__)


class CloudTasksDispatcher:
    """Dispatches asynchronous analysis jobs to Google Cloud Tasks."""

    def __init__(
        self,
        client: Optional[tasks_v2.CloudTasksClient] = None,
        config: Optional[Settings] = None,
        storage: Optional[JobStorageInterface] = None,
    ) -> None:
        """Initializes dispatcher with Google Cloud Tasks client and queue configuration.

        Args:
            client: Optional pre-configured CloudTasksClient instance (used for tests/mocks).
            config: Optional Settings instance (defaults to app.config.settings).
            storage: Optional JobStorageInterface for recording dispatch state.
        """
        self.config = config or settings
        self.project = (
            self.config.AURA_CLOUD_TASKS_PROJECT
            or self.config.GOOGLE_CLOUD_PROJECT
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
        self.location = self.config.AURA_CLOUD_TASKS_LOCATION
        self.queue = self.config.AURA_CLOUD_TASKS_QUEUE
        self.worker_url = self.config.AURA_CLOUD_TASKS_WORKER_URL
        self.service_account = self.config.AURA_CLOUD_TASKS_SERVICE_ACCOUNT
        self.audience = self.config.AURA_OIDC_AUDIENCE or self.worker_url
        self.dispatch_deadline_seconds = getattr(
            self.config, "AURA_CLOUD_TASKS_DISPATCH_DEADLINE_SECONDS", 600
        )
        self.storage = storage

        if client is not None:
            self._client = client
        else:
            try:
                self._client = tasks_v2.CloudTasksClient()
            except Exception as exc:
                logger.error("Failed to initialize Google Cloud Tasks client: %s", exc)
                raise RuntimeError(
                    f"Could not initialize Cloud Tasks client. Verify Google Application Default Credentials: {exc}"
                ) from exc

    def get_task(self, job_id: str) -> Optional[Any]:
        """Looks up a deterministic task in Cloud Tasks.

        Returns:
            The Task object if found, or None if NotFound.
        """
        task_id = f"aura-job-{job_id}"
        task_path = self._client.task_path(self.project, self.location, self.queue, task_id)
        try:
            return self._client.get_task(name=task_path)
        except google_exceptions.NotFound:
            return None

    def enqueue_analysis_job(
        self,
        job_id: str,
        attempt_id: Optional[str] = None,
    ) -> str:
        """Enqueues an analysis job as an authenticated HTTP Cloud Task.

        Args:
            job_id: Unique analysis job identifier.
            attempt_id: Optional attempt UUID for tracking retries.

        Returns:
            The fully qualified Cloud Tasks task name.

        Raises:
            RuntimeError: If configuration is missing or task creation fails.
        """
        if not self.project:
            raise RuntimeError(
                "AURA_CLOUD_TASKS_PROJECT or GOOGLE_CLOUD_PROJECT must be configured for Cloud Tasks execution."
            )
        if not self.worker_url:
            raise RuntimeError(
                "AURA_CLOUD_TASKS_WORKER_URL must be configured with the Cloud Run worker endpoint URL."
            )

        queue_path = self._client.queue_path(self.project, self.location, self.queue)
        
        # Deterministic task name for Cloud Tasks deduplication window
        task_id = f"aura-job-{job_id}"
        task_path = self._client.task_path(self.project, self.location, self.queue, task_id)

        task_payload: Dict[str, Any] = {
            "job_id": job_id,
            "attempt_id": attempt_id or str(uuid.uuid4()),
        }
        body_bytes = json.dumps(task_payload).encode("utf-8")

        # Configure HTTP request with OIDC token for secure service-to-service auth
        http_request_kwargs: Dict[str, Any] = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": self.worker_url,
            "headers": {"Content-Type": "application/json"},
            "body": body_bytes,
        }

        if self.service_account:
            http_request_kwargs["oidc_token"] = tasks_v2.OidcToken(
                service_account_email=self.service_account,
                audience=self.audience,
            )

        http_request = tasks_v2.HttpRequest(**http_request_kwargs)
        
        # Set explicit dispatch deadline bounding maximum worker execution time
        dispatch_deadline = duration_pb2.Duration(seconds=int(self.dispatch_deadline_seconds))
        task = tasks_v2.Task(
            name=task_path,
            http_request=http_request,
            dispatch_deadline=dispatch_deadline,
        )

        try:
            created_task = self._client.create_task(
                parent=queue_path,
                task=task,
            )
            logger.info(
                "Cloud Task enqueued successfully: job_id=%s, task_name=%s, queue=%s",
                job_id,
                created_task.name,
                self.queue,
            )
            if self.storage:
                self.storage.record_dispatch_status(job_id, dispatch_status="enqueued")
            return created_task.name

        except google_exceptions.AlreadyExists:
            logger.info(
                "Cloud Task already exists for job %s (task=%s). Treating as idempotent deduplication.",
                job_id,
                task_path,
            )
            if self.storage:
                self.storage.record_dispatch_status(job_id, dispatch_status="enqueued")
            return task_path

        except Exception as exc:
            # Distinguish definitive client errors from ambiguous network/timeout outcomes
            is_definitive = isinstance(
                exc,
                (
                    google_exceptions.InvalidArgument,
                    google_exceptions.NotFound,
                    google_exceptions.PermissionDenied,
                    google_exceptions.Unauthenticated,
                    google_exceptions.FailedPrecondition,
                ),
            )
            if not is_definitive:
                # Ambiguous outcome (e.g. DeadlineExceeded, ServiceUnavailable, response lost)
                logger.warning(
                    "Cloud Task enqueue returned ambiguous error for job %s: %s. Performing task lookup.",
                    job_id,
                    exc,
                )
                try:
                    existing_task = self.get_task(job_id)
                    if existing_task is not None:
                        logger.info(
                            "Cloud Task enqueue response was lost, but task lookup confirmed task %s exists.",
                            task_path,
                        )
                        if self.storage:
                            self.storage.record_dispatch_status(job_id, dispatch_status="enqueued")
                        return task_path
                    else:
                        logger.error(
                            "Cloud Task enqueue failed and task lookup confirmed task %s does not exist.",
                            task_path,
                        )
                        is_definitive = True
                except Exception as lookup_exc:
                    logger.warning(
                        "Task lookup also failed (%s) for job %s. Recording dispatch_uncertain.",
                        lookup_exc,
                        job_id,
                    )
                    if self.storage:
                        self.storage.record_dispatch_status(
                            job_id,
                            dispatch_status="dispatch_uncertain",
                            error_message=f"Enqueue uncertain: {exc}; lookup error: {lookup_exc}",
                        )
                    raise RuntimeError(f"Task creation outcome uncertain: {exc}") from exc

            # Definitive enqueue failure: mark enqueue_failed and raise
            err_msg = f"Failed to enqueue Cloud Task for job '{job_id}' on queue '{self.queue}': {exc}"
            logger.error(err_msg)
            if self.storage:
                self.storage.record_dispatch_status(
                    job_id,
                    dispatch_status="enqueue_failed",
                    error_message=err_msg,
                )
            raise RuntimeError(err_msg) from exc
