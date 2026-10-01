/**
 * Too thin to trade (operator decision 2026-10-01, on LPA: "there's no way I will ever trade something like
 * that with a 20-cent spread ... the volume is almost dead"). The backend judges it
 * (`setup_scanner/liquidity.py`): too little traded today, too little in the last five minutes, or buying the
 * desk's size walks the asks too far past the ask. This reads the wire and says it in words. Pure.
 * A thin setup is greyed with its numbers, never hidden: nothing blocks in silence.
 */

export type LiquidityState = 'ok' | 'thin' | 'unknown';

export interface LiquidityWalk {
  qty: number;
  best_ask: number;
  last: number | null;
  avg: number;
  over_ask: number;
  shown: number;
  short: boolean;
  /** The walk past the ask in R of the setup's risk. */
  r: number | null;
}

export interface LiquidityRead {
  state: LiquidityState;
  reasons: string[];
  failed: ('day' | 'pace' | 'book')[];
  unknown: Partial<Record<'day' | 'pace' | 'book', string>>;
  day_dollars: number | null;
  pace_dollars: number | null;
  pace_sec: number;
  walk: LiquidityWalk | null;
  as_of: number | null;
  limits: { day_dollars: number; pace_dollars: number; walk_r: number } | null;
}

type Obj = Record<string, unknown>;

function obj(v: unknown): Obj | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function strs(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

const CHECKS = new Set(['day', 'pace', 'book']);

/** A reading off the wire; null when absent (an older backend) or not a reading. */
export function normalizeLiquidity(raw: unknown): LiquidityRead | null {
  const r = obj(raw);
  if (!r || (r.state !== 'ok' && r.state !== 'thin' && r.state !== 'unknown')) return null;
  const w = obj(r.walk);
  const best = num(w?.best_ask);
  const walk: LiquidityWalk | null = w && best !== null && num(w.qty) !== null && num(w.avg) !== null
    ? { qty: num(w.qty) as number, best_ask: best, last: num(w.last), avg: num(w.avg) as number,
      over_ask: num(w.over_ask) ?? 0, shown: num(w.shown) ?? 0, short: w.short === true, r: num(w.r) }
    : null;
  const unknownRaw = obj(r.unknown) ?? {};
  const unknown: LiquidityRead['unknown'] = {};
  for (const [k, v] of Object.entries(unknownRaw)) {
    if (CHECKS.has(k) && typeof v === 'string') unknown[k as 'day' | 'pace' | 'book'] = v;
  }
  const lim = obj(r.limits);
  const day = num(lim?.day_dollars);
  const pace = num(lim?.pace_dollars);
  return {
    state: r.state,
    reasons: strs(r.reasons),
    failed: strs(r.failed).filter((x): x is 'day' | 'pace' | 'book' => CHECKS.has(x)),
    unknown,
    day_dollars: num(r.day_dollars),
    pace_dollars: num(r.pace_dollars),
    pace_sec: num(r.pace_sec) ?? 300,
    walk,
    as_of: num(r.as_of),
    limits: day !== null && pace !== null ? { day_dollars: day, pace_dollars: pace, walk_r: num(lim?.walk_r) ?? 0.25 } : null,
  };
}

export function isThin(read: LiquidityRead | null | undefined): boolean {
  return read?.state === 'thin';
}

/** "$1.25M", "$42K", "$800"; "?" when unknown. */
export function money(x: number | null): string {
  if (x === null) return '?';
  if (x >= 1e6) return `$${(x / 1e6).toFixed(2)}M`;
  if (x >= 1e3) return `$${Math.round(x / 1e3).toLocaleString('en-US')}K`;
  return `$${Math.round(x).toLocaleString('en-US')}`;
}

function ruleLine(read: LiquidityRead): string {
  const l = read.limits;
  if (!l) return '';
  return `Too thin to trade: under ${money(l.day_dollars)} traded today, under ${money(l.pace_dollars)} in the last `
    + `${Math.round(read.pace_sec / 60)} minutes, or buying your size walks the asks more than ${l.walk_r}R past `
    + 'the ask. Nova never buys it, never proposes it, and its score stays out of the read-out.';
}

function sentence(text: string): string {
  return text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}.` : '';
}

/** The hover for a thin (or any) reading: what failed, the numbers, what was not known, the rule. */
export function liquidityTip(read: LiquidityRead): string {
  const lines: string[] = [];
  if (read.state === 'thin') lines.push(...read.reasons.map(sentence));
  else if (read.state === 'ok') {
    lines.push(`${money(read.day_dollars)} traded today, ${money(read.pace_dollars)} in the last `
      + `${Math.round(read.pace_sec / 60)} minutes: liquid enough.`);
  }
  for (const why of Object.values(read.unknown)) if (why) lines.push(`Not known: ${why}.`);
  const rule = ruleLine(read);
  if (rule) lines.push(rule);
  return lines.join('\n');
}

/** The chip a thin setup carries on its row: "Too thin", with the numbers on hover; null otherwise. */
export function thinChip(read: LiquidityRead | null | undefined): { text: string; title: string; tip: string } | null {
  if (!read || read.state !== 'thin') return null;
  return { text: 'Too thin', title: 'Too thin to trade', tip: liquidityTip(read) };
}
