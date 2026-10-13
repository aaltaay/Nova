/**
 * Every order-lock flip, written to the backend log (ADR 045 amendment, operator ask 2026-10-13).
 *
 * At 17:39 ET the operator sent a screenshot of a Paper ticket reading "Market view behind · locked", and
 * nothing on record said which stock, when or why: the desk judged the lock and told no one. Each flip --
 * locked with its reason, or open again after how long -- now goes to `POST /api/market-view/lock`, one log
 * line beside the IBKR lines that explain it. Fire-and-forget; the sample desk sends none.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { VIEW_LOCK_REPORT_PATH } from '../constantGroups/market_view';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { onViewLockFlip } from './viewRegistry';

const REASON_MAX = 600;

export function reportViewLockFlip(symbol: string, why: string | null, lockedForMs: number | null): void {
  if (onSampleDesk()) return;
  const body = JSON.stringify({
    schema_version: 1,
    symbol,
    locked: why != null,
    reason: why ? why.slice(0, REASON_MAX) : null,
    locked_for_ms: lockedForMs != null ? Math.round(lockedForMs) : null,
  });
  void novaFetch(`${API_URL}${VIEW_LOCK_REPORT_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch((err) => console.debug('[Nova] order lock report POST failed', err));
}

/** Start reporting this window's lock flips; returns the stop. */
export function startViewLockReport(): () => void {
  onViewLockFlip(reportViewLockFlip);
  return () => onViewLockFlip(null);
}
