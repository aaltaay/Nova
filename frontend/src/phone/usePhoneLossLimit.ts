/**
 * The daily loss limit (ADR 056) for the venue on screen: how much of the Account line is used.
 * Read from the desk's own route on the desk's own beat. The phone never sets a limit.
 */
import { useEffect, useState } from 'react';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { fetchLossLimit, type LossLimitView } from '../loss_limit/lossLimitApi';
import { LOSS_LIMIT_POLL_MS } from '../loss_limit/lossLimitWords';

export interface PhoneLossLimit {
  /** Dollars lost against the Account line today; null when Nova could not count it. */
  used: number | null;
  /** The Account line, dollars. */
  limit: number | null;
  /** The line has tripped: new buys are stopped, in the desk's words. */
  stopped: string | null;
  warned: boolean;
  /** Why it could not be read or counted; null while it can. */
  error: string | null;
}

export const NO_LOSS_LIMIT: PhoneLossLimit = { used: null, limit: null, stopped: null, warned: false, error: null };

/** The Account line of `venue` in one read. Pure. */
export function lossLimitFor(view: LossLimitView | null, venue: DeskVenue): PhoneLossLimit {
  if (!view) return NO_LOSS_LIMIT;
  const account = view.accounts[venue];
  const line = account?.lines.account;
  const loss = line?.loss ?? account?.loss ?? null;
  return {
    used: loss == null || !Number.isFinite(loss) ? null : Math.max(0, loss),
    limit: Number.isFinite(view.settings.limit_usd) ? view.settings.limit_usd : null,
    stopped: line?.no_new_buys?.text ?? null,
    warned: line?.warned_at != null,
    error: view.error ?? view.settings.error ?? account?.unknown ?? null,
  };
}

export function usePhoneLossLimit(venue: DeskVenue): PhoneLossLimit {
  const [view, setView] = useState<LossLimitView | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    let busy = false;
    const read = (): void => {
      if (busy || document.hidden) return;
      busy = true;
      fetchLossLimit().then(
        (next) => { if (live) { setView(next); setFailed(null); } },
        (err: unknown) => { if (live) setFailed(err instanceof Error ? err.message : String(err)); },
      ).finally(() => { busy = false; });
    };
    read();
    const timer = window.setInterval(read, LOSS_LIMIT_POLL_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  const line = lossLimitFor(view, venue);
  return failed ? { ...line, error: failed } : line;
}
