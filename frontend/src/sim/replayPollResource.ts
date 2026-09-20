/** One cancelable request per resource, scheduled after completion, shared by subscribers. */
import { replayRequest } from './replayRequest';
export interface ReplayResourceState<T> { data: T | null; error: string | null }
export function replayPollResource<T>(path: string, interval: (data: T | null) => number) {
  let state: ReplayResourceState<T> = { data: null, error: null };
  const listeners = new Set<() => void>();
  let controller: AbortController | null = null;
  let timer: number | undefined;
  let generation = 0;
  const publish = (next: ReplayResourceState<T>) => { state = next; listeners.forEach(listener => listener()); };
  const cancel = () => {
    generation++;
    window.clearTimeout(timer);
    timer = undefined;
    controller?.abort();
    controller = null;
  };
  const refresh = async () => {
    if (controller || !listeners.size) return;
    window.clearTimeout(timer);
    const version = generation;
    const request = new AbortController();
    controller = request;
    try {
      const data = await replayRequest<T>(path, { signal: request.signal });
      if (version === generation) publish({ data, error: null });
    } catch (error) {
      if (version === generation && !request.signal.aborted) publish({ ...state, error: error instanceof Error ? error.message : String(error) });
    } finally {
      if (version === generation) {
        controller = null;
        if (listeners.size) timer = window.setTimeout(() => void refresh(), interval(state.data));
      }
    }
  };
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      if (listeners.size === 1) void refresh();
      return () => {
        listeners.delete(listener);
        if (!listeners.size) { cancel(); state = { data: null, error: null }; }
      };
    },
    refresh,
    setData(data: T | null) { publish({ data, error: null }); },
    invalidate(data: T | null = null) { cancel(); publish({ data, error: null }); void refresh(); },
    /** Fence an in-flight GET before a state-changing POST. */
    suspend: cancel,
    resume() { if (listeners.size && !controller) { window.clearTimeout(timer); timer = window.setTimeout(() => void refresh(), interval(state.data)); } },
  };
}
