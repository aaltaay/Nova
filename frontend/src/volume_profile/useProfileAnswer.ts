/**
 * The two pieces of state behind the 5-minute pane's profiles (ADR 058): each profile's answer from the backend, and
 * today's anchor. An answer is asked again while it is `filling` and after the backend did not answer (a restart, a
 * dropped connection), so a profile never stays missing until the switch is toggled. The anchor the operator dragged
 * belongs to one stock's day: on another day or stock it is 09:30 again, never a time outside the day it measures.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchVolumeProfile, type ProfileAnswer, type ProfileKind } from './volumeProfileApi';
import { VP_RETRY_MS } from './volumeProfileConstants';

const NONE: ProfileAnswer = { profile: null, filling: false, error: null };
const NO_ANSWER = 'the backend did not answer';

/** One profile; asked again while `filling` or after no answer, else every `refreshMs` (0: never). */
export function useProfileAnswer(
  kind: ProfileKind, symbol: string, enabled: boolean, day: string | null, anchorEpoch: number | null, refreshMs: number,
): ProfileAnswer {
  const [answer, setAnswer] = useState<ProfileAnswer>(NONE);
  useEffect(() => {
    setAnswer(NONE);
  }, [symbol, day]);
  useEffect(() => {
    if (!enabled || day == null || (kind === 'today' && anchorEpoch == null)) return undefined;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const again = (ms: number) => {
      if (ms > 0 && !ctrl.signal.aborted) timer = setTimeout(ask, ms);
    };
    function ask() {
      fetchVolumeProfile(symbol, kind, day as string, anchorEpoch, ctrl.signal)
        .then((next) => {
          setAnswer(next);
          again(next.filling ? VP_RETRY_MS : refreshMs);
        })
        .catch((err: unknown) => {
          if (ctrl.signal.aborted) return;
          console.warn(`Volume profile (${kind}) for ${symbol} failed:`, err);
          setAnswer({ profile: null, filling: false, error: NO_ANSWER });
          again(VP_RETRY_MS);
        });
    }
    ask();
    return () => {
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [kind, symbol, enabled, day, anchorEpoch, refreshMs]);
  return answer;
}

type AnchorUpdate = number | null | ((prev: number | null) => number | null);

/** Today's anchor in chart seconds, null meaning 09:30; back to null on another stock or day. The setter is stable and
 * always writes for the stock and day on screen, so a drag handler attached earlier never sets a stale day's anchor. */
export function useSessionAnchor(symbol: string, day: string | null): [number | null, (next: AnchorUpdate) => void] {
  const key = `${symbol}|${day}`;
  const keyRef = useRef(key);
  keyRef.current = key;
  const [held, setHeld] = useState<{ key: string; anchor: number | null }>({ key, anchor: null });
  const set = useCallback((next: AnchorUpdate) => {
    setHeld((prev) => {
      const now = keyRef.current;
      const current = prev.key === now ? prev.anchor : null;
      return { key: now, anchor: typeof next === 'function' ? next(current) : next };
    });
  }, []);
  return [held.key === key ? held.anchor : null, set];
}
