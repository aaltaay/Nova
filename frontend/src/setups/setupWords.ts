/**
 * Every setup's words (ADR 031): a board row's state, trigger, distance, tape and
 * grade said in the setup's own terms, each with the hover that explains it in
 * full (ux/hoverTip.ts -- operator ask 2026-09-24: "we are going to need lots of
 * hovers, explaining in detail what each means"). The Bots page's setup cards
 * and Watchlist › Setups read the same words, so a chip means one thing
 * everywhere. Pure: rows in, words out.
 */
import { BOT_SETUP_LABELS, BOT_SETUP_SHORT } from '../constantGroups/bot';
import {
  SETUP_FT_BROKE_LABEL,
  SETUP_FT_BROKE_TIP,
  SETUP_FUNNEL_TIPS,
  SETUP_FUNNEL_WORDS,
  SETUP_GRADE_TIP,
  SETUP_PILLAR_WORDS,
  SETUP_STATE_LABELS,
  SETUP_STATE_TITLES,
  SETUP_TYPE_STATE_LABELS,
  SETUP_TYPE_STATE_TIPS,
  SETUP_WINDOW_WORDS,
  TAPE_UNREAD_TIP,
  TAPE_VERDICT_TIPS,
} from '../constantGroups/setups';
import { catalystTitle, fmtCents, fmtPx, fmtR, isActionable } from './setupsFormat';
import { flowLine } from './flowWords';
import type { SetupCounts, SetupRow, SetupSummary, TapeRead } from './types';

export const FIRST_PULLBACK = 'first_pullback';

/** A chip: its text, the tip's heading and body. */
export interface Words {
  text: string;
  title: string;
  tip: string;
}

/** The setup a row, proposal or scoreboard names; an older API's are the first pullback's. */
export function setupTypeOf(x: { setup_type?: string | null } | null | undefined): string {
  return x?.setup_type || FIRST_PULLBACK;
}

export function setupLabel(id: string | null | undefined): string {
  return BOT_SETUP_LABELS[id ?? ''] ?? id ?? '';
}

export function setupShort(id: string | null | undefined): string {
  return BOT_SETUP_SHORT[id ?? ''] ?? setupLabel(id);
}

/** Eastern wall-clock HH:MM of an epoch second; blank when unknown. */
export function etHm(ts: number | null | undefined): string {
  if (!ts || !Number.isFinite(ts)) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

/** A fraction as a signed percent with a real minus: 0.182 -> "+18%", -0.041 -> "−4.1%". */
export function signedPct(fraction: number | null | undefined): string {
  if (fraction == null || !Number.isFinite(fraction)) return '';
  const pct = fraction * 100;
  const digits = Math.abs(pct) >= 10 ? 0 : 1;
  const text = Math.abs(pct).toFixed(digits);
  return `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${text}%`;
}

/** Backend prose writes ASCII " -- "; a hover sets it as a dash. */
function prose(text: string | null | undefined): string {
  return (text ?? '').replace(/ -- /g, ' — ');
}

const TRIGGER_WORDS: Record<string, string> = {
  first_pullback: 'the last pullback candle\'s high',
  bull_flag: 'the last flag candle\'s high',
  flat_top_breakout: 'the high of day',
  red_to_green: 'the open',
};

const STOP_WORDS: Record<string, string> = {
  first_pullback: 'the pullback low',
  bull_flag: 'the flag low',
  flat_top_breakout: 'the base low',
  red_to_green: 'the lowest low since the open',
};

const TARGET_WORDS: Record<string, string> = {
  first_pullback: 'the leg high or 2R, whichever is higher',
  bull_flag: 'the pole high or 2R, whichever is higher',
  flat_top_breakout: 'R x the risk over the entry',
  red_to_green: 'R x the risk (or the high of day)',
};

function holdMode(row: SetupRow): boolean {
  return setupTypeOf(row) === 'flat_top_breakout' && row.setup?.detail?.entry_mode !== 'break';
}

function broke(row: SetupRow): boolean {
  return holdMode(row) && row.state === 'near' && Boolean(row.setup?.detail?.broke_at);
}

/** The context the setup grew from, in one line ("Pole: 3 green candles, +6.2% to 4.35"). */
function contextLine(row: SetupRow): string {
  const leg = row.leg;
  if (!leg) return '';
  const type = setupTypeOf(row);
  if (type === 'bull_flag') {
    const bars = leg.bars ? `${leg.bars} green candle${leg.bars === 1 ? '' : 's'}, ` : '';
    return `Pole: ${bars}${signedPct(leg.pct)} to ${fmtPx(leg.high)} (from ${fmtPx(leg.low)}).`;
  }
  if (type === 'flat_top_breakout') {
    return `High of day ${fmtPx(leg.high)} on a ${signedPct(leg.pct)} impulse (from ${fmtPx(leg.low)}).`;
  }
  if (type === 'red_to_green') {
    const red = leg.bars != null ? ` · ${leg.bars} close${leg.bars === 1 ? '' : 's'} under it` : '';
    return `Open ${fmtPx(leg.high)} · now ${signedPct(leg.pct)} from it · low ${fmtPx(leg.low)}${red}.`;
  }
  return `Leg ${signedPct(leg.pct)} to a new high ${fmtPx(leg.high)} (from ${fmtPx(leg.low)}).`;
}

/** Trigger, entry, stop, risk and target 1 in one line. */
function levelsLine(row: SetupRow): string {
  const s = row.setup;
  if (!s) return '';
  const waitingHold = holdMode(row) && row.state !== 'triggered';
  const parts = [
    `Trigger ${fmtPx(s.trigger)}`,
    `entry ${waitingHold ? 'the hold candle\'s close +1c' : fmtPx(s.entry)}`,
    `stop ${waitingHold ? 'the hold candle\'s low' : fmtPx(s.stop)}`,
  ];
  if (waitingHold) parts.push('risk and target 1 from the hold candle');
  else parts.push(`risk ${fmtCents(s.risk)} a share`, `target 1 ${fmtPx(s.target1)}`);
  return `${parts.join(' · ')}.`;
}

function stateText(row: SetupRow): string {
  const type = setupTypeOf(row);
  const base = SETUP_TYPE_STATE_LABELS[type]?.[row.state] ?? SETUP_STATE_LABELS[row.state] ?? row.state;
  const s = row.setup;
  switch (row.state) {
    case 'leg': {
      if (type === 'flat_top_breakout') return base;
      if (type === 'bull_flag') return row.leg?.bars ? `${base} · ${row.leg.bars} green` : base;
      const pct = signedPct(row.leg?.pct);
      return pct ? `${base} ${pct}` : base;
    }
    case 'armed':
      if (type === 'bull_flag') return `${base} · ${s?.detail?.flag_bars ?? s?.pullback_bars ?? '?'} bars`;
      if (type === 'flat_top_breakout') return `${base} · ${s?.pullback_bars ?? '?'} bars`;
      if (type === 'red_to_green') {
        const pct = signedPct(row.leg?.pct);
        return pct ? `${base} ${pct}` : base;
      }
      return base;
    case 'near':
      return broke(row) ? SETUP_FT_BROKE_LABEL : base;
    case 'triggered': {
      const at = etHm(s?.triggered_at);
      return at ? `${base} ${at}` : base;
    }
    case 'failed': {
      const at = etHm(row.failed_at);
      return at ? `${base} ${at}` : base;
    }
    default:
      return base;
  }
}

/** The state chip: in the setup's words, with what it means, the numbers and the scanner's own reason. */
export function stateWords(row: SetupRow): Words {
  const type = setupTypeOf(row);
  const text = stateText(row);
  const meaning = SETUP_TYPE_STATE_TIPS[type]?.[row.state] ?? SETUP_STATE_TITLES[row.state] ?? '';
  const lines = [meaning];
  if (broke(row)) {
    const s = row.setup!;
    lines.push(SETUP_FT_BROKE_TIP(fmtPx(s.trigger), etHm(s.detail?.broke_at), s.detail?.hold_bars ?? 3));
  }
  const context = contextLine(row);
  if (context) lines.push(context);
  if (row.setup && row.state !== 'leg') lines.push(levelsLine(row));
  if (row.state === 'triggered' && row.setup) {
    const at = etHm(row.setup.triggered_at);
    const px = row.setup.trigger_price != null ? ` at ${fmtPx(row.setup.trigger_price)}` : '';
    lines.push(`Triggered${at ? ` ${at} ET` : ''}${px}. So far: ${outcomeWords(row)}.`);
  }
  if (row.reason) lines.push(`Now: ${prose(row.reason)}`);
  return { text, title: `${text} · ${setupLabel(type)}`, tip: lines.filter(Boolean).join('\n') };
}

function outcomeWords(row: SetupRow): string {
  if (row.outcome === 'target_first') return `target 1 first${row.bar_r != null ? ` (${fmtR(row.bar_r)})` : ''}`;
  if (row.outcome === 'stop_first') return `the stop first${row.bar_r != null ? ` (${fmtR(row.bar_r)})` : ''}`;
  return row.bar_r != null ? `still open, ${fmtR(row.bar_r)}` : 'still open';
}

/** The trigger cell: the price, and what it is for this setup. */
export function triggerWords(row: SetupRow): Words {
  const s = row.setup;
  const type = setupTypeOf(row);
  if (!s) {
    return {
      text: '·',
      title: 'No trigger yet',
      tip: 'The trigger is set when the setup arms. Until then the scanner is still watching the pattern form.',
    };
  }
  const what = TRIGGER_WORDS[type] ?? 'the level';
  const lines = [`Trigger ${fmtPx(s.trigger)}: ${what}. Trading over it starts the trade.`];
  if (holdMode(row)) {
    lines.push('Hold entry: after the break, the first candle that holds over the high and closes green is the entry, at its close +1c.');
  } else {
    lines.push(`Entry ${fmtPx(s.entry)} (the trigger +1c, the bot's limit).`);
  }
  if (holdMode(row) && row.state !== 'triggered') {
    lines.push('Stop: the hold candle\'s low. The risk and target 1 follow from it.');
  } else {
    const stopIs = holdMode(row) ? 'the hold candle\'s low' : STOP_WORDS[type] ?? 'the stop';
    lines.push(`Stop ${fmtPx(s.stop)}: ${stopIs}. Risk ${fmtCents(s.risk)} a share.`);
    lines.push(`Target 1 ${fmtPx(s.target1)}: ${TARGET_WORDS[type] ?? 'target 1'}. Half comes off there and the stop moves to the entry.`);
  }
  return { text: fmtPx(s.trigger), title: `Trigger · ${setupLabel(type)}`, tip: lines.join('\n') };
}

/** The last-price cell. */
export function lastWords(row: SetupRow): Words {
  const last = row.last_price;
  return {
    text: fmtPx(last),
    title: 'Last',
    tip: last == null ? 'The scanner has no price for this symbol yet.' : `The last price the scanner saw for ${row.symbol}: ${fmtPx(last)}.`,
  };
}

/** How far to go: cents under the trigger while armed or near; how it went once triggered. */
export function toGoWords(row: SetupRow): Words {
  const s = row.setup;
  if (row.state === 'triggered') {
    const text = row.bar_r != null ? fmtR(row.bar_r) : 'open';
    return {
      text,
      title: 'How it went',
      tip: `Since the trigger: ${outcomeWords(row)}. Scored with the research exit rules (half at target 1, the stop to the entry) — a score, not a fill.`,
    };
  }
  if (!isActionable(row) || row.distance == null || !s) {
    return { text: '·', title: 'To go', tip: 'The distance to the trigger is shown once the setup is armed.' };
  }
  const cents = Math.round(row.distance * 100);
  const text = cents <= 0 ? 'at' : cents < 100 ? `${cents}¢` : `$${row.distance.toFixed(2)}`;
  const tip = cents <= 0
    ? `At the ${fmtPx(s.trigger)} trigger now (last ${fmtPx(row.last_price)}).`
    : `${cents}¢ under the ${fmtPx(s.trigger)} trigger (last ${fmtPx(row.last_price)}). Within a few cents it reads Near, and the tape is read there.`;
  return { text, title: 'To go', tip };
}

function metricsLine(tape: TapeRead): string {
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
  if (wall != null && wall > 0 && wallPx != null) parts.push(`biggest seller at the level ${shares(wall)} at ${fmtPx(wallPx)}`);
  const win = num('window_sec');
  return parts.length ? `${parts.join(' · ')}${win != null ? ` (last ${win} s)` : ''}.` : '';
}

function shares(v: number): string {
  if (v >= 1000) return `${(v / 1000).toFixed(v >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(v));
}

/** The tape chip: GO / WAIT / VETO / BLIND, and why, with the numbers the gate read. */
export function tapeWords(row: SetupRow): Words | null {
  const tape = row.tape;
  if (!tape) {
    if (!isActionable(row)) return null;
    return { text: '·', title: 'Tape', tip: TAPE_UNREAD_TIP };
  }
  const v = tape.verdict;
  const lines = [TAPE_VERDICT_TIPS[v] ?? v];
  const reasons = (tape.reasons ?? []).map(prose).filter(Boolean);
  if (reasons.length) lines.push(`Why: ${reasons.join('; ')}.`);
  const metrics = metricsLine(tape);
  if (metrics) lines.push(metrics);
  if (tape.flow) lines.push(flowLine(tape.flow));
  if (!isActionable(row)) lines.push('This is the last read, taken while the setup was armed or near.');
  return { text: String(v).toUpperCase(), title: `Tape · ${row.symbol}`, tip: lines.join('\n') };
}

const PILLAR_ORDER: [string, string][] = [
  ['price', 'price'], ['change', 'change_pct'], ['rvol', 'rvol'], ['float', 'float'], ['news', 'news'],
];

function pillarValue(key: string, p: NonNullable<SetupRow['pillars']>): string {
  switch (key) {
    case 'price': return p.price != null ? fmtPx(p.price) : 'unknown';
    case 'change_pct': return p.change_pct != null ? `+${p.change_pct.toFixed(0)}%` : 'unknown';
    case 'rvol': return p.rvol != null ? `${p.rvol.toFixed(1)}x` : 'unknown';
    case 'float': return p.float != null ? `${(p.float / 1e6).toFixed(1)}M` : 'unknown';
    case 'news': return p.headline ? p.headline : p.news == null ? 'not read' : p.news ? 'a catalyst' : 'none';
    default: return '';
  }
}

/** The grade chip: A / B / C, each pillar with its value, and what the News pillar rested on. */
export function gradeWords(row: SetupRow): Words {
  const p = row.pillars;
  if (!row.grade || !p) {
    return { text: '·', title: 'Grade', tip: `${SETUP_GRADE_TIP}\nGraded when the setup arms.` };
  }
  const checks = (p as { checks?: Record<string, boolean | null> }).checks ?? {};
  const lines = [SETUP_GRADE_TIP];
  for (const [checkKey, valueKey] of PILLAR_ORDER) {
    const ok = checks[checkKey];
    const mark = ok === true ? '✓' : ok === false ? '✗' : '?';
    lines.push(`${mark} ${SETUP_PILLAR_WORDS[valueKey] ?? valueKey}: ${pillarValue(valueKey, p)}`);
  }
  const note = (p as { float_note?: string | null }).float_note;
  if (note) lines.push(`Float: ${prose(note)}`);
  lines.push(catalystTitle(p));
  return { text: row.grade, title: `Grade ${row.grade}`, tip: lines.join('\n') };
}

/** The setup's arming window as the card's status line says it. */
export function windowWords(summary: SetupSummary | null | undefined): string {
  const w = summary?.window;
  if (!w) return '';
  if (w.state === 'before') return SETUP_WINDOW_WORDS.before(w.start);
  if (w.state === 'after') return SETUP_WINDOW_WORDS.after(w.end);
  return SETUP_WINDOW_WORDS.open(w.start, w.end);
}

export interface FunnelStep {
  key: keyof SetupCounts;
  n: number;
  word: string;
  tip: string;
}

/** Today's funnel for a setup card: forming -> armed -> near -> triggered, then failed and proposed. */
export function funnelSteps(setup: string, counts: SetupCounts | null | undefined): FunnelStep[] {
  if (!counts) return [];
  const w = SETUP_FUNNEL_WORDS[setup] ?? SETUP_FUNNEL_WORDS[FIRST_PULLBACK];
  const steps: FunnelStep[] = [
    { key: 'forming', n: counts.forming, word: w.forming, tip: SETUP_FUNNEL_TIPS.forming },
    { key: 'armed', n: counts.armed, word: w.armed, tip: SETUP_FUNNEL_TIPS.armed },
    { key: 'near', n: counts.near, word: w.near, tip: SETUP_FUNNEL_TIPS.near },
    { key: 'triggered', n: counts.triggered, word: w.triggered, tip: SETUP_FUNNEL_TIPS.triggered },
    { key: 'failed', n: counts.failed, word: 'failed', tip: SETUP_FUNNEL_TIPS.failed },
    { key: 'proposed', n: counts.proposed, word: 'proposed', tip: SETUP_FUNNEL_TIPS.proposed },
  ];
  if (counts.filtered > 0) {
    steps.push({ key: 'filtered', n: counts.filtered, word: 'filtered', tip: SETUP_FUNNEL_TIPS.filtered });
  }
  return steps;
}

/** One symbol can sit in two setups: the tag naming the others (ADR 031). */
export function otherSetups(row: SetupRow, all: readonly SetupRow[]): string[] {
  const type = setupTypeOf(row);
  return all
    .filter(r => r.symbol === row.symbol && setupTypeOf(r) !== type)
    .map(r => setupTypeOf(r));
}

/** How far along a row is -- the Watchlist and Symbols cards show a symbol's most advanced setup. */
const RANK: Record<string, number> = {
  near: 0, armed: 1, triggered: 2, pullback: 3, leg: 4, filtered: 5, failed: 6, watching: 7,
};

export function rowRank(row: SetupRow): number {
  return RANK[row.state] ?? 9;
}

/** Every row a symbol has on the board, most advanced first. */
export function rowsBySymbol(rows: readonly SetupRow[] | null | undefined): Map<string, SetupRow[]> {
  const out = new Map<string, SetupRow[]>();
  for (const r of rows ?? []) {
    const list = out.get(r.symbol);
    if (list) list.push(r);
    else out.set(r.symbol, [r]);
  }
  for (const list of out.values()) list.sort((a, b) => rowRank(a) - rowRank(b));
  return out;
}
