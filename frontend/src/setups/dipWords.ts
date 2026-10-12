/**
 * The pullback dip's words (#847, operator ask 2026-10-12): the first pullback's run and pullback, bought at the
 * candle that bottoms it -- a bottoming wick or the first green close -- with the pullback's high as target 1.
 * WATCH ONLY: the eyes draw and score it, Nova never trades it. Its "trigger" is no level a price crosses: it is
 * the close of the candle that bottomed the pullback, bought a cent over. `setupWords.ts` asks here for a dip row;
 * the chart's drawing (`stock_read/dipShapes.ts`) names the candle the same way. Pure: rows in, words out.
 */
import { fmtCents, fmtPx } from './setupsFormat';
import { targetSentence } from './targets';
import type { SetupLevels } from './types';

export const PULLBACK_DIP = 'pullback_dip';

/** The template's two entries, as the chart and the hovers name them. */
export const DIP_ENTRY_NAMES: Record<string, string> = {
  wick: 'a bottoming wick',
  green: 'the first green close',
};
/** The candle's short tag on the chart. */
export const DIP_ENTRY_TAGS: Record<string, string> = {
  wick: 'WICK',
  green: '1ST GREEN',
};
export const DIP_WATCH_ONLY_LINE = 'Watch only: Nova draws and scores it, and never trades it — no alert, no bot, no Auto-entry, no Approve.';

export function isDip(x: { setup_type?: string | null } | null | undefined): boolean {
  return x?.setup_type === PULLBACK_DIP;
}

function pct(x: number | null | undefined): string {
  return x == null || !Number.isFinite(x) ? '?' : `${Math.round(x * 100)}%`;
}

/** The entry candle in a few words: "a bottoming wick (7c, 78% of the candle, closing 89% up it)". */
export function dipCandleWords(s: Pick<SetupLevels, 'detail'>): string {
  const d = s.detail ?? {};
  const mode = String(d.entry_mode ?? 'wick');
  const name = DIP_ENTRY_NAMES[mode] ?? 'the candle that bottomed it';
  if (mode === 'green') {
    const red = d.red_bars ?? null;
    return red != null ? `${name} after ${red} red candle${red === 1 ? '' : 's'}` : name;
  }
  if (d.lower_wick == null) return name;
  return `${name} (${fmtCents(d.lower_wick)} of lower wick, ${pct(d.wick_pct)} of the candle, closing ${pct(d.close_pct)} up it)`;
}

/** The trigger cell's hover for a dip: what was bought, where, the stop and the targets. */
export function dipTriggerLines(s: SetupLevels): string[] {
  const d = s.detail ?? {};
  const low = typeof d.pullback_low === 'number' ? ` ${fmtPx(d.pullback_low)}` : '';
  return [
    `Bought the dip at the ${fmtPx(s.trigger)} close of the candle that bottomed the pullback: ${dipCandleWords(s)}.`,
    `Entry ${fmtPx(s.entry)} (the close +1c: a limit over the close, never the ask chased).`,
    `Stop ${fmtPx(s.stop)}: under the pullback's low${low}. Risk ${fmtCents(s.risk)} a share.`,
    targetSentence(s),
    DIP_WATCH_ONLY_LINE,
  ];
}

/** Entry, stop, risk and target 1 in one line, the dip's way. */
export function dipLevelsLine(s: SetupLevels): string {
  return `Bought at the ${fmtPx(s.trigger)} close · entry ${fmtPx(s.entry)} · stop ${fmtPx(s.stop)} · risk `
    + `${fmtCents(s.risk)} a share · target 1 ${fmtPx(s.target1)}.`;
}

/** The context the dip grew from: the run, and the pullback's length. */
export function dipContextLine(leg: { high: number; low: number; pct: number }, bars: number | null | undefined): string {
  const run = `Run +${(leg.pct * 100).toFixed(1)}% to ${fmtPx(leg.high)} (from ${fmtPx(leg.low)})`;
  return bars ? `${run}, then a pullback of ${bars} candle${bars === 1 ? '' : 's'}.` : `${run}.`;
}
