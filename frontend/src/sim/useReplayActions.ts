import { useCallback, useEffect, useRef, useState } from 'react';
import { replayPost, replayRequest } from './replayRequest';
import { SIM_HISTORY_REQUEST_FAILED } from './simConstants';
import { serializeSimSessionMutation } from './simSessionMutations';

/** Actions own independent busy/error state and release on timeout or unmount. */
export function useReplayActions() {
  const pending = useRef(new Map<string, AbortController>());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    const actions = pending.current;
    return () => { actions.forEach(controller => controller.abort()); actions.clear(); };
  }, []);
  const request = useCallback(async <T,>(key: string, path: string, body: unknown = {}, failure = SIM_HISTORY_REQUEST_FAILED): Promise<T | undefined> => {
    if (pending.current.has(key)) return;
    const controller = new AbortController();
    pending.current.set(key, controller);
    setBusy(new Set(pending.current.keys()));
    setErrors(old => { const next = { ...old }; delete next[key]; return next; });
    try {
      const data = await serializeSimSessionMutation(path, () => replayRequest<T>(path, { ...replayPost(body), signal: controller.signal }, failure));
      if (!controller.signal.aborted) return data;
    } catch (error) {
      if (!controller.signal.aborted) setErrors(old => ({ ...old, [key]: error instanceof Error ? error.message : String(error) }));
    } finally {
      pending.current.delete(key);
      if (!controller.signal.aborted) setBusy(new Set(pending.current.keys()));
    }
  }, []);
  return { request, busy, errors };
}
