/**
 * A short setup's story on the chart (ADR 049): its context, its levels and what price did next, said the short way.
 * The backend reads a short's aftermath on prices turned upside down (`eyes/aftermath.py`), then sends real prices:
 * `level` is the low it was building over, `floor` the high it would have stopped at, and `first: "low"` means it
 * broke down first -- the move a short waits for. `pastSetups.ts` asks here for a short. Pure.
 */
import { isShortSetup } from '../constantGroups/short_setups';
import { fmtPx } from './planMath';
import { hhmmEt } from './timeWords';
import type { SetupLeg } from './types';

/** The short scanners' rules in a few words, for a label on the chart; read before the long ones. */
export const SHORT_RULE_WORDS: [RegExp, string][] = [
  [/not a lower high/, 'bounce made the high'],
  [/took back [\d.]+% of the fade/, 'bounce too deep'],
  [/closed over the 9 EMA/, 'closed over the 9 EMA'],
  [/new low under the fade/, 'new low under the fade'],
  [/the bounce made a new low/, 'new low first'],
  [/minutes passed without a fill/, 'not filled in time'],
  [/flag took back/, 'flag too deep'],
  [/highest-volume candle is green/, 'green volume candle'],
  [/no breakdown within/, 'no breakdown'],
  [/closed back over/, 'back over the level'],
  [/MACD positive/, 'MACD positive'],
  [/a newer fade took over/, 'a newer fade'],
];

export function isShortEpisode(x: { setup_type?: string | null } | null | undefined): boolean {
  return isShortSetup(x?.setup_type);
}

function drop(x: number): string {
  return `−${(Math.abs(x) * 100).toFixed(1)}%`;
}

/** What a short grew from, in one line. */
export function shortLegLine(setupType: string, leg: SetupLeg): string {
  switch (setupType) {
    case 'backside_lower_high':
      return `Fade ${drop(leg.pct)} off the ${fmtPx(leg.high)} high of day, to ${fmtPx(leg.low)}`;
    case 'bear_flag':
      return `Pole ${drop(leg.pct)} to ${fmtPx(leg.low)} (from ${fmtPx(leg.high)})`;
    case 'failed_breakout':
      return `Flat top ${fmtPx(leg.low)}, poked to ${fmtPx(leg.high)} at ${hhmmEt(leg.t)}`;
    case 'lost_vwap':
      return `Lost VWAP ${fmtPx(leg.high)} at ${hhmmEt(leg.t)}`;
    case 'ssr_bounce':
      return `Dropped ${drop(leg.pct)} to ${fmtPx(leg.low)} under SSR`;
    default:
      return '';
  }
}

/** Its levels, the short way: the short under the trigger, the buy stop over it, the cover under the entry. */
export function shortArmedLine(lv: { trigger: number; stop: number; target1: number }, armed: boolean): string {
  return `${armed ? 'Armed' : 'Would arm'} ▼ SHORT: under ${fmtPx(lv.trigger)}, buy stop ${fmtPx(lv.stop)}, cover `
    + `${fmtPx(lv.target1)}`;
}

const SHORT_OUTCOME_WORDS: Record<string, string> = {
  target_first: 'the cover came first',
  stop_first: 'the buy stop came first',
  open: 'neither the cover nor the buy stop within 15 minutes',
};

export function shortOutcomeWords(outcome: string | null | undefined): string | null {
  return outcome ? SHORT_OUTCOME_WORDS[outcome] ?? null : null;
}

function r(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(2)}R`;
}

/** What price did after a short failed or faded: under its level first (the breakdown) or over its stop. */
export function shortAfterLines(a: {
  window_min: number; level: number; floor: number | null; first: string; crossed_at: number | null;
  high: number | null; low: number | null;
  trade: { entry: number; stop: number; target: number; outcome: string; mfe_r: number | null; mae_r: number | null;
    bar_r: number | null } | null;
}): string[] {
  const stop = a.floor === null ? 'its high (not known)' : fmtPx(a.floor);
  const level = fmtPx(a.level);
  const at = a.crossed_at !== null ? ` at ${hhmmEt(a.crossed_at)}` : '';
  const head = `Next ${a.window_min} min: `;
  const out: string[] = [];
  if (a.first === 'low') out.push(`${head}under ${level} first${at} (the breakdown it waited for), before ${stop}.`);
  else if (a.first === 'high') out.push(`${head}over ${stop} first${at}, before ${level}.`);
  else if (a.first === 'neither') out.push(`${head}neither under ${level} nor over ${stop}.`);
  else if (a.first === 'pending') out.push(`${head}neither under ${level} nor over ${stop} yet.`);
  else out.push(`${head}no chart bars after it -- not known.`);
  if (a.high !== null && a.low !== null) out.push(`It traded ${fmtPx(a.low)} to ${fmtPx(a.high)} then.`);
  const t = a.trade;
  if (t) {
    out.push(`The refused short: under ${fmtPx(t.entry)}, buy stop ${fmtPx(t.stop)}, cover ${fmtPx(t.target)} -- `
      + `${SHORT_OUTCOME_WORDS[t.outcome] ?? t.outcome}; best ${r(t.mfe_r)}, worst ${r(t.mae_r)}; bar exits ${r(t.bar_r)}.`);
  }
  out.push('Scored on the 1-minute bars, not fills.');
  return out;
}
