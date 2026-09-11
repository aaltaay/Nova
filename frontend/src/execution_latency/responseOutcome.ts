import type { BrowserExecutionTiming } from './browserTiming';

type ExecutionResultBody = {
  ok?: boolean;
  error?: string | null;
  detail?: unknown;
};

/** FastAPI HTTPException bodies are `{detail: ...}` with no `ok` / `error`. */
function detailAsError(detail: unknown): string | null {
  if (typeof detail === 'string') return detail.trim() || null;
  if (Array.isArray(detail)) {
    // Pydantic validation errors: [{loc, msg, type}, …].
    const messages = detail
      .map(item =>
        item && typeof item === 'object' && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : '',
      )
      .filter(Boolean);
    return messages.length ? messages.join('; ') : null;
  }
  if (detail && typeof detail === 'object') {
    const msg = (detail as { msg?: unknown; error?: unknown }).msg
      ?? (detail as { error?: unknown }).error;
    if (typeof msg === 'string') return msg.trim() || null;
  }
  return null;
}

/**
 * Parse the execution body before closing browser timing. Nova commonly
 * returns HTTP 200 for a handled execution rejection, so transport status
 * alone is not an operation outcome.
 *
 * An HTTP error body carries the real reason in `detail` (D-013): promote it
 * to `error` and mark `ok: false` so the ticket shows the reject reason
 * instead of a generic "Order failed".
 */
export async function parseTimedExecutionResponse<
  T extends ExecutionResultBody,
>(
  response: Response,
  timing: BrowserExecutionTiming,
): Promise<T> {
  try {
    const body = await response.json() as T;
    const ok = response.ok && body.ok !== false;
    timing.complete(ok);
    if (ok || body.error) return body;
    const fromDetail = detailAsError(body.detail);
    if (!fromDetail) return { ...body, ok: false } as T;
    return { ...body, ok: false, error: fromDetail } as T;
  } catch (error) {
    timing.complete(false);
    throw error;
  }
}
