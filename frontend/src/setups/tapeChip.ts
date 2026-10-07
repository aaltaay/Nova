/**
 * The tape chip (ADR 022, ADR 049): GO / WAIT / VETO / BLIND and why, with the numbers the gate read. A short's
 * head is the mirror's (red at the bid, no buyer holding the level); the reasons are the backend's own words,
 * already mirrored. Pure.
 */
import { TAPE_UNREAD_TIP, TAPE_VERDICT_TIPS } from '../constantGroups/setups';
import { flowLine } from './flowWords';
import { fmtCents, fmtPx, isActionable, prose } from './setupsFormat';
import { isShortRow, shortTapeTip } from './shortWords';
import type { SetupRow, TapeRead } from './types';

/** One chip: its text, the tip's heading and body (`setupWords.Words`). */
interface ChipWords {
  text: string;
  title: string;
  tip: string;
}

function metricsLine(tape: TapeRead, short = false): string {
  const m = tape.metrics ?? {};
  const num = (k: string) => (typeof m[k] === 'number' && Number.isFinite(m[k] as number) ? (m[k] as number) : null);
  const parts: string[] = [];
  const bid = num('best_bid');
  const ask = num('best_ask');
  if (bid != null && ask != null) parts.push(`bid ${fmtPx(bid)} × ask ${fmtPx(ask)}`);
  const spread = num('spread');
  if (spread != null) parts.push(`spread ${fmtCents(spread)}`);
  const askN = num('ask_prints');
  const bidN = num('bid_prints');
  if (askN != null || bidN != null) {
    const askV = num('ask_volume') ?? 0;
    const bidV = num('bid_volume') ?? 0;
    parts.push(`${askN ?? 0} prints at the ask (${shares(askV)}) vs ${bidN ?? 0} at the bid (${shares(bidV)})`);
  }
  const wall = num('wall_size');
  const wallPx = num('wall_price');
  if (wall != null && wall > 0 && wallPx != null) parts.push(`biggest ${short ? 'buyer' : 'seller'} at the level ${shares(wall)} at ${fmtPx(wallPx)}`);
  const win = num('window_sec');
  return parts.length ? `${parts.join(' · ')}${win != null ? ` (last ${win} s)` : ''}.` : '';
}

function shares(v: number): string {
  if (v >= 1000) return `${(v / 1000).toFixed(v >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(v));
}

/** The tape chip: GO / WAIT / VETO / BLIND, and why, with the numbers the gate read. */
export function tapeWords(row: SetupRow): ChipWords | null {
  const tape = row.tape;
  if (!tape) {
    if (!isActionable(row)) return null;
    return { text: '·', title: 'Tape', tip: TAPE_UNREAD_TIP };
  }
  const v = tape.verdict;
  const short = isShortRow(row);
  const lines = [(short ? shortTapeTip(v) : null) ?? TAPE_VERDICT_TIPS[v] ?? v];
  const reasons = (tape.reasons ?? []).map(prose).filter(Boolean);
  if (reasons.length) lines.push(`Why: ${reasons.join('; ')}.`);
  const metrics = metricsLine(tape, short);
  if (metrics) lines.push(metrics);
  if (tape.flow) lines.push(flowLine(tape.flow));
  if (!isActionable(row)) lines.push('This is the last read, taken while the setup was armed or near.');
  return { text: String(v).toUpperCase(), title: `Tape · ${row.symbol}`, tip: lines.join('\n') };
}
