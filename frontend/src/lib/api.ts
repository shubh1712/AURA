import {
  AnalysisRequest,
  AnalysisResponse,
  HealthResponse,
  AnalysisJobCreateRequest,
  AnalysisJobStatusResponse,
} from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

export class ApiClientError extends Error {
  statusCode?: number;
  details?: unknown;

  constructor(message: string, statusCode?: number, details?: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

/**
 * Extracts a normalized, user-facing error message and raw details from a failed response.
 */
async function extractErrorInfo(res: Response): Promise<{
  errorMessage: string;
  details: unknown;
}> {
  let errorMessage = `Request failed (${res.status} ${res.statusText})`;
  let details: unknown = null;

  try {
    const errorJson = await res.json();
    details = errorJson;

    if (res.status === 504) {
      errorMessage = "The decision analysis exceeded its allowed processing time.";
      if (typeof errorJson.detail === "string") {
        errorMessage = `${errorMessage} (${errorJson.detail})`;
      } else if (
        errorJson.detail &&
        typeof errorJson.detail === "object" &&
        "message" in errorJson.detail
      ) {
        errorMessage = `${errorMessage} (${(errorJson.detail as { message: unknown }).message})`;
      }
    } else if (Array.isArray(errorJson.detail)) {
      // FastAPI validation error array
      errorMessage = errorJson.detail
        .map((d: { msg?: string; loc?: string[] }) => d.msg || JSON.stringify(d))
        .join("; ");
    } else if (typeof errorJson.detail === "string") {
      errorMessage = errorJson.detail;
    } else if (
      errorJson.detail &&
      typeof errorJson.detail === "object" &&
      "message" in errorJson.detail
    ) {
      errorMessage = String(errorJson.detail.message);
    } else if (errorJson.message) {
      errorMessage = errorJson.message;
    }
  } catch {
    // Response was not JSON
    if (res.status === 504) {
      errorMessage = "The decision analysis exceeded its allowed processing time.";
    }
  }

  return { errorMessage, details };
}

/**
 * Health check ping to FastAPI backend.
 */
export async function checkHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    });

    if (!res.ok) {
      throw new ApiClientError(
        `Backend health check failed with status ${res.status}`,
        res.status
      );
    }

    return await res.json();
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    throw new ApiClientError(
      `Could not connect to AURA backend at ${API_BASE_URL}. Ensure the FastAPI server is running.`,
      undefined,
      error
    );
  }
}

/**
 * Submit decision for staging / initial intake analysis to the real FastAPI endpoint:
 * POST /api/analyze
 */
export async function analyzeDecision(
  payload: AnalysisRequest
): Promise<AnalysisResponse> {
  const url = `${API_BASE_URL}/api/analyze`;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const { errorMessage, details } = await extractErrorInfo(res);
      throw new ApiClientError(errorMessage, res.status, details);
    }

    const data = await res.json();

    if (
      !data ||
      typeof data !== "object" ||
      typeof data.analysis_id !== "string" ||
      typeof data.status !== "string" ||
      typeof data.question !== "string" ||
      typeof data.message !== "string"
    ) {
      throw new ApiClientError(
        "Malformed response received from AURA decision engine.",
        res.status,
        data
      );
    }

    return data as AnalysisResponse;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }

    throw new ApiClientError(
      `Network error: unable to reach AURA engine at ${url}. Please verify that the backend is running.`,
      undefined,
      error
    );
  }
}

/**
 * Submit an asynchronous decision analysis job:
 * POST /api/analysis/jobs
 */
export async function createAnalysisJob(
  payload: AnalysisJobCreateRequest,
  ownerId?: string | null
): Promise<AnalysisJobStatusResponse> {
  const url = `${API_BASE_URL}/api/analysis/jobs`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const effectiveOwner = ownerId || payload.owner_id;
  if (effectiveOwner) {
    headers["X-Owner-Id"] = effectiveOwner;
  }

  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const { errorMessage, details } = await extractErrorInfo(res);
      throw new ApiClientError(errorMessage, res.status, details);
    }

    const data = await res.json();

    if (
      !data ||
      typeof data !== "object" ||
      typeof data.job_id !== "string" ||
      typeof data.status !== "string" ||
      typeof data.stage !== "string"
    ) {
      throw new ApiClientError(
        "Malformed job creation response received from AURA engine.",
        res.status,
        data
      );
    }

    return data as AnalysisJobStatusResponse;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }

    throw new ApiClientError(
      `Network error: unable to reach AURA engine at ${url}. Please verify that the backend is running.`,
      undefined,
      error
    );
  }
}

/**
 * Poll current execution status and stage of an asynchronous analysis job:
 * GET /api/analysis/jobs/{job_id}
 */
export async function getAnalysisJobStatus(
  jobId: string,
  ownerId?: string | null
): Promise<AnalysisJobStatusResponse> {
  let url = `${API_BASE_URL}/api/analysis/jobs/${encodeURIComponent(jobId)}`;
  if (ownerId) {
    url += `?owner_id=${encodeURIComponent(ownerId)}`;
  }
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (ownerId) {
    headers["X-Owner-Id"] = ownerId;
  }

  try {
    const res = await fetch(url, {
      method: "GET",
      headers,
    });

    if (!res.ok) {
      const { errorMessage, details } = await extractErrorInfo(res);
      throw new ApiClientError(errorMessage, res.status, details);
    }

    const data = await res.json();

    if (
      !data ||
      typeof data !== "object" ||
      typeof data.job_id !== "string" ||
      typeof data.status !== "string" ||
      typeof data.stage !== "string"
    ) {
      throw new ApiClientError(
        "Malformed job status response received from AURA engine.",
        res.status,
        data
      );
    }

    return data as AnalysisJobStatusResponse;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }

    throw new ApiClientError(
      `Network error: unable to reach AURA engine at ${url}. Please verify that the backend is running.`,
      undefined,
      error
    );
  }
}

/**
 * Retrieve completed AnalysisResponse payload for an asynchronous job:
 * GET /api/analysis/jobs/{job_id}/result
 */
export async function getAnalysisJobResult(
  jobId: string,
  ownerId?: string | null
): Promise<AnalysisResponse> {
  let url = `${API_BASE_URL}/api/analysis/jobs/${encodeURIComponent(jobId)}/result`;
  if (ownerId) {
    url += `?owner_id=${encodeURIComponent(ownerId)}`;
  }
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (ownerId) {
    headers["X-Owner-Id"] = ownerId;
  }

  try {
    const res = await fetch(url, {
      method: "GET",
      headers,
    });

    if (!res.ok) {
      const { errorMessage, details } = await extractErrorInfo(res);
      throw new ApiClientError(errorMessage, res.status, details);
    }

    const data = await res.json();

    if (
      !data ||
      typeof data !== "object" ||
      typeof data.analysis_id !== "string" ||
      typeof data.status !== "string" ||
      typeof data.question !== "string"
    ) {
      throw new ApiClientError(
        "Malformed job result response received from AURA engine.",
        res.status,
        data
      );
    }

    return data as AnalysisResponse;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }

    throw new ApiClientError(
      `Network error: unable to reach AURA engine at ${url}. Please verify that the backend is running.`,
      undefined,
      error
    );
  }
}
