/**
 * Classify why the local/remote Nova API is unreachable so the header can show
 * a stable flag (API_DOWN / API_WEDGED / …) instead of a vague "Backend unreachable".
 */
import {
  API_URL,
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_HTTP,
  BACKEND_DIAG_FLAG_UNREACHABLE,
  BACKEND_DIAG_FLAG_WEDGED,
  BACKEND_DIAG_HINTS,
  BACKEND_PROBE_TIMEOUT_MS,
} from '../constants';

export type BackendDiagFlag =
  | typeof BACKEND_DIAG_FLAG_DOWN
  | typeof BACKEND_DIAG_FLAG_WEDGED
  | typeof BACKEND_DIAG_FLAG_HTTP
  | typeof BACKEND_DIAG_FLAG_UNREACHABLE;

export interface BackendDiagnosis {
  flag: BackendDiagFlag;
  /** Short user-facing line (no flag code). */
  message: string;
  /** One-line remediation for tooltip / console. */
  hint: string;
  /** Milliseconds spent probing (when measured). */
  probe_ms?: number;
  http_status?: number;
}

function abortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const name = (err as { name?: string }).name;
  return name === 'AbortError' || name === 'TimeoutError';
}

/**
 * Probe GET /api/health with a short timeout.
 * - Fast network failure → API_DOWN (nothing listening / refused)
 * - Abort/timeout → API_WEDGED (hung process holding the port — last night's failure mode)
 * - Non-OK HTTP → API_HTTP
 */
export async function diagnoseBackend(
  probeTimeoutMs: number = BACKEND_PROBE_TIMEOUT_MS,
): Promise<BackendDiagnosis> {
  const started = performance.now();
  try {
    const res = await fetch(`${API_URL}/health`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(probeTimeoutMs),
    });
    const probe_ms = Math.round(performance.now() - started);
    if (res.ok) {
      // Caller thought we were down, but health is fine now.
      return {
        flag: BACKEND_DIAG_FLAG_UNREACHABLE,
        message: 'Backend unreachable',
        hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_UNREACHABLE],
        probe_ms,
        http_status: res.status,
      };
    }
    return {
      flag: BACKEND_DIAG_FLAG_HTTP,
      message: `Backend HTTP ${res.status}`,
      hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_HTTP],
      probe_ms,
      http_status: res.status,
    };
  } catch (err) {
    const probe_ms = Math.round(performance.now() - started);
    if (abortError(err) || probe_ms >= probeTimeoutMs - 50) {
      return {
        flag: BACKEND_DIAG_FLAG_WEDGED,
        message: 'Backend hung (no health response)',
        hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_WEDGED],
        probe_ms,
      };
    }
    return {
      flag: BACKEND_DIAG_FLAG_DOWN,
      message: 'Backend not running',
      hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_DOWN],
      probe_ms,
    };
  }
}

/** Structured console line agents/humans can grep: `[Nova][API_FLAG] API_WEDGED …` */
export function logBackendDiagnosis(diag: BackendDiagnosis): void {
  console.warn(`[Nova][API_FLAG] ${diag.flag}`, {
    message: diag.message,
    hint: diag.hint,
    probe_ms: diag.probe_ms,
    http_status: diag.http_status,
    health_url: `${API_URL}/health`,
  });
}
