import { useEffect, useRef } from 'react';
import { adviseWsUrl, fetchAdviseRun } from './adviseApi';
import type { AdviseEvent, AdviseRun } from './types';

export function useAdviseStream(
  run: AdviseRun | null,
  onRun: (run: AdviseRun) => void,
): void {
  const onRunRef = useRef(onRun);
  onRunRef.current = onRun;
  const runId = run?.id;
  const status = run?.status;

  useEffect(() => {
    if (!runId || (status !== 'queued' && status !== 'running')) return;
    let closed = false;
    const ws = new WebSocket(adviseWsUrl(runId));
    ws.onmessage = (ev) => {
      let payload: AdviseEvent & { run?: AdviseRun };
      try {
        payload = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (payload.type === 'snapshot' && payload.run) {
        onRunRef.current(payload.run);
        return;
      }
      if (payload.type === 'ping') return;
      void fetchAdviseRun(runId)
        .then((fresh) => {
          if (!closed) onRunRef.current(fresh);
        })
        .catch(() => {
          /* keep last snapshot */
        });
    };
    ws.onerror = () => {
      void fetchAdviseRun(runId).then((fresh) => {
        if (!closed) onRunRef.current(fresh);
      }).catch(() => undefined);
    };
    return () => {
      closed = true;
      ws.close();
    };
  }, [runId, status]);
}
