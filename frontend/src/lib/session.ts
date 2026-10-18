/**
 * AURA Active Analysis Session Management.
 *
 * Implements minimal client-side session referencing for browser refresh restoration:
 * - Persists ONLY minimal identifiers (jobId, analysisId, ownerId, lastUpdated).
 * - NEVER persists full analysis result JSON or simulation datasets to browser storage.
 * - Primary storage: sessionStorage (survives F5 refresh in active tab, clears on tab closure).
 * - Fallback storage: localStorage (for local development session recovery, with 24-hour expiration).
 * - SSR-safe (gracefully handles environments without window/storage).
 */

export interface ActiveAnalysisSession {
  jobId: string;
  analysisId?: string;
  ownerId?: string;
  lastUpdated: string;
}

const STORAGE_KEY = "aura_active_analysis_session";
const MAX_SESSION_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

/**
 * Saves or updates the active analysis session reference.
 */
export function saveActiveSession(
  session: Partial<ActiveAnalysisSession> & { jobId?: string; analysisId?: string }
): void {
  if (!isBrowser()) return;

  try {
    const existing = loadActiveSession();
    const effectiveJobId = session.jobId || existing?.jobId || "";
    const effectiveAnalysisId = session.analysisId || existing?.analysisId;
    const effectiveOwnerId = session.ownerId !== undefined ? session.ownerId : existing?.ownerId;

    if (!effectiveJobId && !effectiveAnalysisId) {
      return;
    }

    const payload: ActiveAnalysisSession = {
      jobId: effectiveJobId,
      analysisId: effectiveAnalysisId,
      ownerId: effectiveOwnerId,
      lastUpdated: new Date().toISOString(),
    };

    const serialized = JSON.stringify(payload);
    window.sessionStorage.setItem(STORAGE_KEY, serialized);

    try {
      window.localStorage.setItem(STORAGE_KEY, serialized);
    } catch {
      // Ignore localStorage quota or policy exceptions
    }
  } catch (err) {
    console.warn("Failed to save AURA active analysis session:", err);
  }
}

/**
 * Loads the active analysis session reference if present and valid.
 * Checks sessionStorage first, falling back to localStorage within the age limit.
 */
export function loadActiveSession(): ActiveAnalysisSession | null {
  if (!isBrowser()) return null;

  try {
    let raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      try {
        raw = window.localStorage.getItem(STORAGE_KEY);
      } catch {
        raw = null;
      }
    }

    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<ActiveAnalysisSession>;
    if (!parsed || typeof parsed !== "object") return null;

    if (!parsed.jobId && !parsed.analysisId) return null;

    // Check expiration if lastUpdated timestamp exists
    if (parsed.lastUpdated) {
      const updatedTime = new Date(parsed.lastUpdated).getTime();
      if (!isNaN(updatedTime) && Date.now() - updatedTime > MAX_SESSION_AGE_MS) {
        clearActiveSession();
        return null;
      }
    }

    return {
      jobId: String(parsed.jobId || ""),
      analysisId: parsed.analysisId ? String(parsed.analysisId) : undefined,
      ownerId: parsed.ownerId ? String(parsed.ownerId) : undefined,
      lastUpdated: parsed.lastUpdated || new Date().toISOString(),
    };
  } catch (err) {
    console.warn("Failed to parse AURA active analysis session:", err);
    clearActiveSession();
    return null;
  }
}

/**
 * Clears the active analysis session from all client-side storages.
 * Called when the user explicitly clicks "New Analysis" or when an analysis is confirmed deleted/expired.
 */
export function clearActiveSession(): void {
  if (!isBrowser()) return;

  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }

  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }
}

/**
 * Returns true if an active analysis session reference currently exists.
 */
export function hasActiveSession(): boolean {
  return loadActiveSession() !== null;
}
