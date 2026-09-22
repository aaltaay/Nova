/** One cancelable request per resource, scheduled after completion, shared by subscribers. */
import { replayRequest } from './replayRequest';

/**
 * `data` is the last good answer. After a failed poll it is kept (a blip must
 * not blank the desk) and `stale` says so, with `error` naming the failure --
 * a reader showing money or a clock must mark stale figures, never pass them
 * off as current (QA 2026-09-22, C44).
 */
export interface ReplayResourceState<T> { data: T | null; error: string | null; stale?: boolean }

export interface ReplayPollOptions<T> {
  /** Validate the raw body at the boundary; a throw reads as a failed poll. */
  parse?: (raw: unknown) => T;
  /** What a failure without a server message says ("Sim clock request failed (500)"). */
  failure?: string;
  /**
   * Drop kept data once the last good answer is older than this and polls keep
   * failing -- for figures that must not outlive their source (money).
   */
  maxStaleMs?: number;
}

export function replayPollResource<T>(
  path: string,
  interval: (data: T | null) => number,
  options: ReplayPollOptions<T> = {},
) {
  const { parse, failure, maxStaleMs } = options;
  let state: ReplayResourceState<T> = { data: null, error: null, stale: false };
  const listeners = new Set<() => void>();
  let controller: AbortController | null = null;
  let timer: number | undefined;
  let generation = 0;
  let lastGoodAt: number | null = null;
  const accept = (raw: unknown): T => (parse ? parse(raw) : raw as T);
  const publish = (next: ReplayResourceState<T>) => { state = next; listeners.forEach(listener => listener()); };
  const publishData = (data: T | null) => {
    lastGoodAt = data == null ? null : Date.now();
    publish({ data, error: null, stale: false });
  };
  const publishFailure = (message: string) => {
    const expired = maxStaleMs != null && lastGoodAt != null && Date.now() - lastGoodAt > maxStaleMs;
    if (expired) lastGoodAt = null;
    const data = expired ? null : state.data;
    publish({ data, error: message, stale: data != null });
  };
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
      const raw = await replayRequest<unknown>(path, { signal: request.signal }, failure);
      const data = accept(raw);
      if (version === generation) publishData(data);
    } catch (error) {
      if (version === generation && !request.signal.aborted) {
        publishFailure(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (version === generation) {
        controller = null;
        if (listeners.size) timer = window.setTimeout(() => void refresh(), interval(state.data));
      }
    }
  };
  /** Data handed in by a command reply goes through the same boundary as a poll. */
  const acceptGiven = (data: T | null): boolean => {
    if (data == null) { publishData(null); return true; }
    try {
      publishData(accept(data));
      return true;
    } catch (error) {
      console.warn(`replay resource ${path}: rejected an unreadable reply`, error);
      publishFailure(error instanceof Error ? error.message : String(error));
      return false;
    }
  };
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      if (listeners.size === 1) void refresh();
      return () => {
        listeners.delete(listener);
        if (!listeners.size) { cancel(); lastGoodAt = null; state = { data: null, error: null, stale: false }; }
      };
    },
    refresh,
    setData(data: T | null) { acceptGiven(data); },
    invalidate(data: T | null = null) { cancel(); acceptGiven(data); void refresh(); },
    /** Fence an in-flight GET before a state-changing POST. */
    suspend: cancel,
    resume() { if (listeners.size && !controller) { window.clearTimeout(timer); timer = window.setTimeout(() => void refresh(), interval(state.data)); } },
  };
}
