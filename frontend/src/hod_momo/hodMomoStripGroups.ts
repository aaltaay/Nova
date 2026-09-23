/**
 * One strip row per ticker per batch (operator ask, 2026-09-23): when one
 * ticker fires several strategies together, the strip shows one row with a
 * count bubble instead of a row per strategy. Pure; no module state.
 *
 * "Together" is the backend's consolidation batch: a symbol's alerts wait
 * `master.consolidation_sec` and leave at once, one per strategy, each stamped
 * with its own newest fire. A group is one ticker's alerts raised within the
 * window of its oldest member, at most one per strategy -- the same strategy
 * again is a re-fire and starts a new row. Groups are built oldest first, so
 * an arriving alert only ever joins the newest group or opens one: rows never
 * re-shuffle and a row's key (its oldest member) never changes.
 */
import { HOD_MOMO_STRIP_CARD_GAP_PX, HOD_MOMO_STRIP_CARD_MARGIN_PX } from './hodMomoStripConstants';
import { alertIdentity } from './hodMomoWire';
import { stripAlertMs } from './hodMomoStripRows';
import type { AlertObject } from './types';

export type StripAlertGroup = {
  /** Stable React key: the oldest member's identity. */
  key: string;
  ticker: string;
  /** Newest member: the row's time, price and print note. */
  lead: AlertObject;
  /** Every member, by strategy id (S5, S7, S10 ...). */
  members: AlertObject[];
};

type Building = {
  members: AlertObject[];
  anchorMs: number | null;
  strategies: Set<number>;
  /** Index of the newest member in the newest-first input. */
  leadIndex: number;
};

/**
 * @param alerts Newest first (`stripAlertsForMode`).
 * @param windowSec How far after a group's oldest member an alert may still join it.
 * @returns Groups, newest lead first.
 */
export function groupStripAlerts(alerts: readonly AlertObject[], windowSec: number): StripAlertGroup[] {
  const windowMs = Math.max(0, windowSec) * 1000;
  const built: Building[] = [];
  const openByTicker = new Map<string, Building>();

  for (let i = alerts.length - 1; i >= 0; i -= 1) {
    const alert = alerts[i];
    const ms = stripAlertMs(alert);
    const open = openByTicker.get(alert.ticker);
    if (
      open
      && open.anchorMs != null
      && ms != null
      && Math.abs(ms - open.anchorMs) <= windowMs
      && !open.strategies.has(alert.strategy_id)
    ) {
      open.members.push(alert);
      open.strategies.add(alert.strategy_id);
      open.leadIndex = i;
      continue;
    }
    const next: Building = { members: [alert], anchorMs: ms, strategies: new Set([alert.strategy_id]), leadIndex: i };
    built.push(next);
    openByTicker.set(alert.ticker, next);
  }

  return built
    .sort((a, b) => a.leadIndex - b.leadIndex)
    .map((g) => ({
      key: alertIdentity(g.members[0]),
      ticker: g.members[0].ticker,
      lead: alerts[g.leadIndex],
      members: g.members.length > 1
        ? [...g.members].sort((a, b) => a.strategy_id - b.strategy_id)
        : g.members,
    }));
}

/** The row flags NEW while any member is new. */
export function groupIsNew(group: StripAlertGroup, newIds: ReadonlySet<string>): boolean {
  return group.members.some((m) => newIds.has(alertIdentity(m)));
}

/** Same row content: same members in the same order (memo guard for the strip row). */
export function sameGroup(a: StripAlertGroup, b: StripAlertGroup): boolean {
  if (a === b) return true;
  if (a.key !== b.key || a.lead !== b.lead || a.members.length !== b.members.length) return false;
  return a.members.every((m, i) => m === b.members[i]);
}

/**
 * Where the hover card goes: below the anchor, above it when there is no room
 * below, and kept inside the viewport.
 */
export function stripCardPosition(
  anchor: { left: number; top: number; bottom: number },
  card: { width: number; height: number },
  viewport: { width: number; height: number },
): { left: number; top: number } {
  const m = HOD_MOMO_STRIP_CARD_MARGIN_PX;
  const below = anchor.bottom + HOD_MOMO_STRIP_CARD_GAP_PX;
  const above = anchor.top - HOD_MOMO_STRIP_CARD_GAP_PX - card.height;
  const top = below + card.height <= viewport.height - m || above < m ? below : above;
  const left = Math.min(Math.max(m, anchor.left), Math.max(m, viewport.width - m - card.width));
  return { left, top: Math.max(m, top) };
}
