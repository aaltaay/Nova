import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { SIM_REQUEST_TIMEOUT_MS } from './simConstants';

/** Local replay calls only: cancellation and a useful message even for HTML errors. */
export async function replayRequest<T>(path: string, init: RequestInit = {}, failure = 'Historical replay request failed'): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, SIM_REQUEST_TIMEOUT_MS);
  try {
    const response = await novaFetch(`${API_BASE_URL}${path.startsWith('/api/') ? path : `/api/sim${path}`}`, { ...init, signal: controller.signal });
    const data = typeof response.json === 'function' ? await response.json().catch(() => null) : null;
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `${failure}${response.status ? ` (${response.status})` : ''}`);
    if (data === null) throw new Error('Nova returned an unreadable response. Try again.');
    return data as T;
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
