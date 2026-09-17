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
import type { HealthStatus } from '../types/health';

export type BackendDiagFlag =
  | typeof BACKEND_DIAG_FLAG_DOWN
  | typeof BACKEND_DIAG_FLAG_WEDGED
  | typeof BACKEND_DIAG_FLAG_HTTP
  | typeof BACKEND_DIAG_FLAG_UNREACHABLE;

export interface BackendDiagnosis {
  /** True when GET /api/health returned HTTP 200 -- never paint API-down. */
  ok: boolean;
  flag: BackendDiagFlag;
  /** Short user-facing line (no flag code). */
  message: string;
  /** One-line remediation for tooltip / console. */
  hint: string;
  /** Milliseconds spent probing (when measured). */
  probe_ms?: number;
  http_status?: number;
  /** Parsed /api/health body when the probe succeeded. */
  health?: HealthStatus;
}

function abortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const name = (err as { name?: string }).name;
  return name === 'AbortError' || name === 'TimeoutError';
}

async function readHealthBody(res: Response): Promise<HealthStatus | undefined> {
  try {
    const body = (await res.json()) as unknown;
    if (body && typeof body === 'object') return body as HealthStatus;
  } catch {
    // Health JSON is optional -- 200 alone means the process answered.
  }
  return undefined;
}

/**
 * Probe GET /api/health with a short timeout.
 * - HTTP 200 → ok (a different route may have failed; API is not down)
 * - Fast network failure → API_DOWN (nothing listening / refused)
 * - Abort/timeout → API_WEDGED (hung process holding the port)
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
      const health = await readHealthBody(res);
      return {
        ok: true,
        flag: BACKEND_DIAG_FLAG_UNREACHABLE,
        message: 'Nova API is reachable',
        hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_UNREACHABLE],
        probe_ms,
        http_status: res.status,
        health,
      };
    }
    return {
      ok: false,
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
        ok: false,
        flag: BACKEND_DIAG_FLAG_WEDGED,
        message: 'Backend hung (no health response)',
        hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_WEDGED],
        probe_ms,
      };
    }
    return {
      ok: false,
      flag: BACKEND_DIAG_FLAG_DOWN,
      message: 'Backend not running',
      hint: BACKEND_DIAG_HINTS[BACKEND_DIAG_FLAG_DOWN],
      probe_ms,
    };
  }
}

/**
 * After a mode/scanner route fails, keep last-known connected when health is
 * 200. Never paint disconnected from a successful probe (#238).
 */
export function healthAfterFailedRoute(
  last: HealthStatus | undefined,
  diag: BackendDiagnosis,
): HealthStatus {
  if (diag.ok) {
    const fromProbe = diag.health;
    return {
      status: 'connected',
      latency_ms: fromProbe?.latency_ms ?? diag.probe_ms ?? last?.latency_ms ?? 0,
      health_source: fromProbe?.health_source ?? last?.health_source ?? 'nova_process',
      message: fromProbe?.message ?? last?.message,
      instance_id: fromProbe?.instance_id ?? last?.instance_id,
      pid: fromProbe?.pid ?? last?.pid,
      parent_pid: fromProbe?.parent_pid ?? last?.parent_pid,
      ib_loop_lag_ms: fromProbe?.ib_loop_lag_ms ?? last?.ib_loop_lag_ms,
      http_loop_lag_ms: fromProbe?.http_loop_lag_ms ?? last?.http_loop_lag_ms,
      integrations: fromProbe?.integrations ?? last?.integrations,
    };
  }
  return {
    status: 'disconnected',
    latency_ms: 0,
    message: diag.message,
    flag: diag.flag,
    flag_hint: diag.hint,
    health_source: last?.health_source ?? 'nova_process',
  };
}

/** Structured console line agents/humans can grep: `[Nova][API_FLAG] API_WEDGED …` */
export function logBackendDiagnosis(diag: BackendDiagnosis): void {
  if (diag.ok) return;
  console.warn(`[Nova][API_FLAG] ${diag.flag}`, {
    message: diag.message,
    hint: diag.hint,
    probe_ms: diag.probe_ms,
    http_status: diag.http_status,
    health_url: `${API_URL}/health`,
  });
}
