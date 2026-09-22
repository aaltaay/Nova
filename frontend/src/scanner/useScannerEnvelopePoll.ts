/**
 * Slow poll of GET /api/scan/envelope for persistent-authoritative desks
 * (ADR 008): rows follow /ws/scanner, but mode / health / feed_error and the
 * per-table state only ever came from the mount-time REST fetch, so a
 * premarket -> market switch, a new feed_error or a recovered feed never
 * reached the board (QA C48). This hook re-reads that envelope only -- no rows.
 */
import { useEffect, useRef } from 'react';
import { API_URL } from '../constants';
import { SCANNER_ENVELOPE_POLL_MS } from '../constantGroups/scanner_board';
import { readScannerEnvelope } from './scannerRest';

const ENVELOPE_ROUTE = '/api/scan/envelope';

export function useScannerEnvelopePoll(opts: {
  enabled: boolean;
  onEnvelope: (data: Record<string, unknown>) => void;
  pollMs?: number;
}): void {
  const { enabled, onEnvelope, pollMs = SCANNER_ENVELOPE_POLL_MS } = opts;
  const onEnvelopeRef = useRef(onEnvelope);
  onEnvelopeRef.current = onEnvelope;

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let lastError: string | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      let stop = false;
      try {
        const res = await fetch(`${API_URL}/scan/envelope`, {
          signal: AbortSignal.timeout(pollMs),
        });
        const read = await readScannerEnvelope(res, ENVELOPE_ROUTE);
        if (cancelled) return;
        if (read.ok) {
          lastError = null;
          onEnvelopeRef.current(read.data);
        } else {
          // An older API has no envelope route: say so once and stop asking.
          stop = res.status === 404;
          if (read.error !== lastError) console.warn(`[Nova] ${read.error}`);
          lastError = read.error;
        }
      } catch (err) {
        if (cancelled) return;
        const text = `${ENVELOPE_ROUTE} did not answer`;
        if (text !== lastError) console.warn(`[Nova] ${text}`, err);
        lastError = text;
      }
      if (!cancelled && !stop) timer = setTimeout(poll, pollMs);
    };

    timer = setTimeout(poll, pollMs);
    return () => {
      cancelled = true;
      if (timer != null) clearTimeout(timer);
    };
  }, [enabled, pollMs]);
}
