import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { SIM_REQUEST_FAILED_DEFAULT, SIM_REQUEST_PLAIN_ERROR_MAX_CHARS, SIM_REQUEST_TIMEOUT_MS } from './simConstants';

interface Body { data: unknown; text: string | null }

/** The body as JSON when it parses, plus its raw text (a Starlette 500 is text/plain). */
async function readBody(response: Response): Promise<Body> {
  if (typeof response.text === 'function') {
    const raw = await response.text().catch(() => null);
    if (raw == null) return { data: null, text: null };
    try {
      return { data: JSON.parse(raw), text: raw };
    } catch {
      return { data: null, text: raw };
    }
  }
  if (typeof response.json === 'function') return { data: await response.json().catch(() => null), text: null };
  return { data: null, text: null };
}

/**
 * Why a request failed, in words: the server's own `detail`, else what it
 * answered -- the status, plus a short plain-text body ("Internal Server
 * Error"). An HTML error page is never pasted into the desk.
 */
export function failureMessage(response: Response, body: Body, failure: string): string {
  const detail = (body.data as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string' && detail) return detail;
  const status = response.status ? ` (${response.status})` : '';
  const type = typeof response.headers?.get === 'function' ? response.headers.get('content-type') ?? '' : '';
  const plain = body.text?.trim() ?? '';
  const quote = type.includes('text/plain') && plain && plain.length <= SIM_REQUEST_PLAIN_ERROR_MAX_CHARS
    ? `: ${plain}` : '';
  return `${failure}${status}${quote}`;
}

/** Local replay calls only: cancellation and a useful message even for HTML errors. */
export async function replayRequest<T>(path: string, init: RequestInit = {}, failure = SIM_REQUEST_FAILED_DEFAULT): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, SIM_REQUEST_TIMEOUT_MS);
  try {
    const response = await novaFetch(`${API_BASE_URL}${path.startsWith('/api/') ? path : `/api/sim${path}`}`, { ...init, signal: controller.signal });
    const body = await readBody(response);
    if (!response.ok) throw new Error(failureMessage(response, body, failure));
    if (body.data === null) throw new Error('Nova returned an unreadable response. Try again.');
    return body.data as T;
  } catch (error) {
    if (timedOut) throw new Error('Nova did not respond in time. Try again.');
    if (error instanceof TypeError) throw new Error('Could not reach Nova. Check the connection and try again.');
    throw error;
  } finally {
    window.clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
}

export const replayPost = (body: unknown): RequestInit => ({
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});
