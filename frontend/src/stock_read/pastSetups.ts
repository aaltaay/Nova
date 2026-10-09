/**
 * Setups that ended (ADR 036 amendment, operator ask 2026-09-29): the day's episodes from the eyes'
 * journal -- one per setup's life on the symbol -- and what price did after each failed or faded one
 * (`GET /api/stock-read/{symbol}/past-setups`). This module owns their wire shape and their words: the
 * chart's label -- whole, in a few words and as icons -- and the whole story a hover tells. The drawing
 * is `pastShapes.ts`.
 * Nothing here is estimated: every price is the scanner's or the chart's own bars'.
 */
import { list, normalizeLeg, normalizeSetupLevels, num, obj, str } from './normalize';
import { flatTopStory, flatTopTouches, isFlatTop } from './flatTopShapes';
import { fmtPx, setupName } from './planMath';
import { isShortEpisode, shortAfterLines, shortArmedLine, shortLegLine, shortOutcomeWords, SHORT_RULE_WORDS } from './pastShort';
import { hhmmEt } from './timeWords';
import type { SetupLane, SetupLeg, SetupLevels } from './types';

export type EpisodeEnd = 'failed' | 'faded' | 'triggered' | 'cut';
export type AfterFirst = 'high' | 'low' | 'neither' | 'pending' | 'unknown';
export type TradeOutcome = 'target_first' | 'stop_first' | 'open';

export interface RefusedTrade {
  entry: number;
  stop: number;
  risk: number;
  target: number;
  outcome: TradeOutcome;
  outcome_at: number | null;
  bar_r: number | null;
  exit_reason: string | null;
  mfe_r: number | null;
  mae_r: number | null;
}

/** What price did in the window after a failed or faded setup died. */
export interface EpisodeAfter {
  from_ts: number;
  price: number | null;
  level: number;
  entry: number;
  floor: number | null;
  window_min: number;
  complete: boolean;
  bars: number;
  high: number | null;
  low: number | null;
  first: AfterFirst;
  crossed_at: number | null;
  trade: RefusedTrade | null;
}

export interface EpisodeScore {
  outcome: string | null;
  bar_r: number | null;
  exit_reason: string | null;
}

export interface Episode {
  id: string;
  setup_type: string;
  started_at: number;
  ended_at: number | null;
  end: EpisodeEnd | null;
  died_at: number | null;
  died_bar_t: number | null;
  reason: string | null;
  ended_by: string | null;
  reached: string;
  leg: SetupLeg;
  setup: SetupLevels | null;
  filtered: string | null;
  triggered_at: number | null;
  trigger_price: number | null;
  score: EpisodeScore | null;
  after: EpisodeAfter | null;
}

export interface PastSetups {
  symbol: string;
  date: string;
  generated_at: number;
  /** A Sim replay's (ADR 052 amendment, #815): the Sim eyes' setups up to the playhead, `generated_at` the playhead. */
  replay: boolean;
  episodes: Episode[];
  journal: { ok: boolean; error: string | null };
  bars: { ok: boolean; error: string | null };
}

const ENDS: ReadonlySet<string> = new Set<EpisodeEnd>(['failed', 'faded', 'triggered', 'cut']);
const FIRSTS: ReadonlySet<string> = new Set<AfterFirst>(['high', 'low', 'neither', 'pending', 'unknown']);
const OUTCOMES: ReadonlySet<string> = new Set<TradeOutcome>(['target_first', 'stop_first', 'open']);

function trade(raw: unknown): RefusedTrade | null {
  const t = obj(raw);
  const entry = num(t?.entry);
  const stop = num(t?.stop);
  const risk = num(t?.risk);
  const target = num(t?.target);
  if (!t || entry === null || stop === null || risk === null || target === null) return null;
  return {
    entry, stop, risk, target,
    outcome: typeof t.outcome === 'string' && OUTCOMES.has(t.outcome) ? (t.outcome as TradeOutcome) : 'open',
    outcome_at: num(t.outcome_at),
    bar_r: num(t.bar_r),
    exit_reason: str(t.exit_reason),
    mfe_r: num(t.mfe_r),
    mae_r: num(t.mae_r),
  };
}

function after(raw: unknown): EpisodeAfter | null {
  const a = obj(raw);
  const from = num(a?.from_ts);
  const level = num(a?.level);
  const entry = num(a?.entry);
  if (!a || from === null || level === null || entry === null) return null;
  return {
    from_ts: from,
    price: num(a.price),
    level,
    entry,
    floor: num(a.floor),
    window_min: num(a.window_min) ?? 15,
    complete: a.complete === true,
    bars: num(a.bars) ?? 0,
    high: num(a.high),
    low: num(a.low),
    first: typeof a.first === 'string' && FIRSTS.has(a.first) ? (a.first as AfterFirst) : 'unknown',
    crossed_at: num(a.crossed_at),
    trade: trade(a.trade),
  };
}

function episode(raw: unknown): Episode | null {
  const e = obj(raw);
  const started = num(e?.started_at);
  const leg = normalizeLeg(e?.leg);
  if (!e || typeof e.id !== 'string' || typeof e.setup_type !== 'string' || started === null || !leg) return null;
  const score = obj(e.score);
  return {
    id: e.id,
    setup_type: e.setup_type,
    started_at: started,
    ended_at: num(e.ended_at),
    end: typeof e.end === 'string' && ENDS.has(e.end) ? (e.end as EpisodeEnd) : null,
    died_at: num(e.died_at),
    died_bar_t: num(e.died_bar_t),
    reason: str(e.reason),
    ended_by: str(e.ended_by),
    reached: str(e.reached) ?? 'leg',
    leg,
    setup: normalizeSetupLevels(e.setup),
    filtered: str(e.filtered),
    triggered_at: num(e.triggered_at),
    trigger_price: num(e.trigger_price),
    score: score ? { outcome: str(score.outcome), bar_r: num(score.bar_r), exit_reason: str(score.exit_reason) } : null,
    after: after(e.after),
  };
}

function source(raw: unknown): { ok: boolean; error: string | null } {
  const s = obj(raw);
  return { ok: s?.ok === true, error: str(s?.error) };
}

/** The past setups off the wire; null when it is not one. */
export function normalizePastSetups(raw: unknown): PastSetups | null {
  const r = obj(raw);
  if (!r || typeof r.symbol !== 'string' || !Array.isArray(r.episodes)) return null;
  return {
    symbol: r.symbol,
    date: str(r.date) ?? '',
    generated_at: num(r.generated_at) ?? 0,
    replay: r.replay === true,
    episodes: list(r.episodes, episode),
    journal: source(r.journal),
    bars: source(r.bars),
  };
}

/** The past setups a tab may draw (ADR 052 amendment, #815): this stock's and this desk's -- a replay's on a replay
 * desk -- and on a replay never one read at a later playhead than `simNow` (a rewind draws nothing from later while
 * the next read comes). Pure. */
export function pastNowOf(past: PastSetups | null, symbol: string, replay: boolean,
  simNow: number | null): PastSetups | null {
  if (!past || past.symbol !== symbol || past.replay !== replay) return null;
  return replay && simNow !== null && past.generated_at > simNow + 1 ? null : past;
}

/** How it ended; `failed` for one that failed while its lane still shows it (it is past from then). */
export function endOf(ep: Episode): EpisodeEnd | null {
  return ep.end ?? (ep.died_at !== null ? 'failed' : null);
}

/** Episodes the 1-minute pane draws: failed (from the moment they failed), faded or triggered, on a lane
 * the operator shows -- and past their leg (a faded leg or pole with no pullback, flag or base is the
 * chart's own candles). */
export function drawnPast(episodes: Episode[], hidden: string[]): Episode[] {
  return episodes.filter(e => {
    const end = endOf(e);
    return end !== null && end !== 'cut' && !hidden.includes(e.setup_type) && !(end === 'faded' && e.reached === 'leg');
  });
}

/** Setup types whose lane is failed right now and drawn as past: the live box gives way to it. */
export function failingNow(episodes: Episode[]): Set<string> {
  return new Set(episodes.filter(e => e.end === null && e.died_at !== null).map(e => e.setup_type));
}

/** The scanners' rules in a few words, for a label on the chart (the hover has the whole reason). */
const RULE_WORDS: [RegExp, string][] = [
  ...SHORT_RULE_WORDS,
  [/new high without a fresh/, 'new high, no fresh leg'],
  [/made a higher high/, 'higher high in the flag'],
  [/gave back/, 'gave back too much'],
  [/closed under the 9 EMA|low broke the 9 EMA/, 'lost the 9 EMA'],
  [/off the 9 EMA/, 'too far from the 9 EMA'],
  [/ran past \d+ candles/, 'ran too long'],
  [/topping tail/, 'topping tail'],
  [/volume fell/, 'volume faded'],
  [/not lighter than the pole/, 'heavy flag volume'],
  [/highest-volume candle is red/, 'red volume candle'],
  [/closed more than [\d.]+% under/, 'broke down from the base'],
  [/closed back under/, 'lost the high'],
  [/MACD (negative|below zero)/, 'MACD negative'],
  [/risk [\d.]+.* is over/, 'risk too big'],
  [/risk [\d.]+.* is under/, 'risk too small'],
  [/entry window|window closed/, 'outside the window'],
  [/gapped over the trigger/, 'gapped over the trigger'],
  [/a flag needs|wait for the flag/, 'no flag yet'],
  [/wait for the pullback/, 'no pullback yet'],
  [/wait for a base/, 'no base yet'],
  // The flat top (2026-10-06): it counts its touches before it arms.
  [/wait for candles to tap it|touched once/, 'no taps yet'],
  [/\d+ of \d+ touches/, 'too few taps'],
  [/the flat top has \d+ touch/, 'lost its taps'],
  [/a newer flat top took over/, 'a newer flat top'],
];

/** A reason in a few words: a known rule's name, else its first clause cut to `max` characters. */
export function shortReason(text: string | null | undefined, max = 40): string {
  if (!text) return '';
  for (const [re, words] of RULE_WORDS) if (re.test(text)) return words;
  const first = text.split(' -- ')[0].replace(/\s*\([^)]*\)/g, '').trim();
  return first.length > max ? `${first.slice(0, max - 1).trimEnd()}…` : first;
}

const FIRST_WORDS: Record<AfterFirst, string | null> = {
  high: '↗ then broke out',
  low: '↘ then broke down',
  neither: '→ then went nowhere',
  pending: null,
  unknown: null,
};

/** Which it touched first after the trigger, in a label's words (neither: nothing to say). */
const OUTCOME_SHORT: Record<string, string> = {
  target_first: 'target first',
  stop_first: 'stop first',
};

/** The same, whole, for the hover. */
const OUTCOME_WORDS: Record<string, string> = {
  target_first: 'the target came first',
  stop_first: 'the stop came first',
  open: 'neither the target nor the stop within 15 minutes',
};

function signedR(x: number): string {
  return `${x >= 0 ? '+' : ''}${x.toFixed(1)}R`;
}

/** The label a past setup carries on the chart. */
export function pastLabel(ep: Episode): string {
  const end = endOf(ep);
  if (end === 'triggered') {
    const outcome = ep.score?.outcome ? OUTCOME_SHORT[ep.score.outcome] ?? null : null;
    const r = ep.score?.bar_r;
    return ['✓ triggered', outcome, r !== null && r !== undefined ? signedR(r) : null].filter(Boolean).join(' · ');
  }
  const mark = end === 'failed' ? '✕' : '○';
  const next = ep.after ? FIRST_WORDS[ep.after.first] : null;
  return [`${mark} ${shortReason(ep.reason) || (end === 'failed' ? 'failed' : 'faded')}`, next].filter(Boolean).join(' · ');
}

/** What came next as its arrow alone. */
const FIRST_ARROWS: Record<AfterFirst, string> = { high: '↗', low: '↘', neither: '→', pending: '', unknown: '' };

/** The same in a few words, where the whole label does not fit: "✕ topping tail ↘", "✓ +1.4R". */
export function pastShortLabel(ep: Episode): string {
  const end = endOf(ep);
  if (end === 'triggered') {
    const r = ep.score?.bar_r;
    return r !== null && r !== undefined ? `✓ ${signedR(r)}` : '✓ triggered';
  }
  const mark = end === 'failed' ? '✕' : '○';
  const arrow = ep.after ? FIRST_ARROWS[ep.after.first] : '';
  return [mark, shortReason(ep.reason, 24) || (end === 'failed' ? 'failed' : 'faded'), arrow].filter(Boolean).join(' ');
}

/** Its mark alone -- ✕ failed, ○ faded, ✓ triggered -- on the compact chart, and where even a few words
 * do not fit; the hover tells the rest (operator ask 2026-09-30: "just show (x) and when we hover, it
 * shows the full failed setup"). */
export function pastIconLabel(ep: Episode): string {
  const end = endOf(ep);
  return end === 'triggered' ? '✓' : end === 'failed' ? '✕' : '○';
}

const END_WORDS: Record<EpisodeEnd, string> = {
  failed: 'failed',
  faded: 'faded',
  triggered: 'triggered',
  cut: 'cut off by a restart',
};

function r(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(2)}R`;
}

/** Whole sentences for a past setup's hover: why it ended, where, and what price did next. */
export function pastStory(ep: Episode): { title: string; lines: string[] } {
  const end = endOf(ep);
  const when = hhmmEt(end === 'triggered' ? ep.triggered_at : ep.died_at ?? ep.ended_at);
  const title = `${setupName(ep.setup_type)} · ${end ? END_WORDS[end] : 'on the chart'} ${when}`.trim();
  const lines: string[] = [];
  if (ep.reason) lines.push(`${end === 'failed' ? 'The rule it broke' : end === 'triggered' ? 'Trigger' : 'Waiting on'}: ${ep.reason}`);
  if (ep.filtered) lines.push(`Kept out by the template's filter: ${ep.filtered}`);
  const gone = ep.ended_at !== null
    ? `, gone ${hhmmEt(ep.ended_at)}${ep.ended_by && end !== 'failed' ? ` (${ep.ended_by})` : ''}`
    : end === 'failed' ? '; the scanner still shows it failed' : '';
  const short = isShortEpisode(ep);
  const legLine = short ? shortLegLine(ep.setup_type, ep.leg)
    : `Leg ${ep.leg.pct >= 0 ? '+' : ''}${(ep.leg.pct * 100).toFixed(1)}% to ${fmtPx(ep.leg.high)}`;
  lines.push(`${legLine}; seen ${hhmmEt(ep.started_at)}${gone}`);
  const touches = isFlatTop(ep.setup_type) ? flatTopTouches(ep) : [];
  if (touches.length) lines.push(`Touches: ${touches.map(([t, h]) => `${hhmmEt(t)} ${fmtPx(h)}`).join(' · ')}`);
  if (ep.setup) {
    lines.push(short ? shortArmedLine(ep.setup, true)
      : `Armed: trigger ${fmtPx(ep.setup.trigger)}, stop ${fmtPx(ep.setup.stop)}, target ${fmtPx(ep.setup.target1)}`);
  }
  if (end === 'triggered' && ep.score) {
    const said = (short ? shortOutcomeWords(ep.score.outcome) : null) ?? OUTCOME_WORDS[ep.score.outcome ?? ''];
    lines.push(`Scored: ${said ?? ep.score.outcome ?? 'not yet'}, bar exits ${r(ep.score.bar_r)}`);
  }
  const a = ep.after;
  if (a) lines.push(...(short ? shortAfterLines(a) : afterLines(a)));
  else if (end === 'failed' || end === 'faded') lines.push('What came next: not known (no chart bars were read for it).');
  return { title, lines };
}

function afterLines(a: EpisodeAfter): string[] {
  const floor = a.floor === null ? 'its low (not known)' : fmtPx(a.floor);
  const out: string[] = [];
  const at = a.crossed_at !== null ? ` at ${hhmmEt(a.crossed_at)}` : '';
  const head = `Next ${a.window_min} min: `;
  if (a.first === 'high') out.push(`${head}over ${fmtPx(a.level)} first${at}, before ${floor}.`);
  else if (a.first === 'low') out.push(`${head}under ${floor} first${at}, before ${fmtPx(a.level)}.`);
  else if (a.first === 'neither') out.push(`${head}neither over ${fmtPx(a.level)} nor under ${floor}.`);
  else if (a.first === 'pending') out.push(`${head}neither over ${fmtPx(a.level)} nor under ${floor} yet.`);
  else out.push(`${head}no chart bars after it -- not known.`);
  if (a.high !== null && a.low !== null) out.push(`It traded ${fmtPx(a.low)} to ${fmtPx(a.high)} then.`);
  const t = a.trade;
  if (t) {
    out.push(`The refused trade: entry ${fmtPx(t.entry)}, stop ${fmtPx(t.stop)}, target ${fmtPx(t.target)} -- `
      + `${OUTCOME_WORDS[t.outcome]}; best ${r(t.mfe_r)}, worst ${r(t.mae_r)}; bar exits ${r(t.bar_r)}.`);
  }
  out.push('Scored on the 1-minute bars, not fills.');
  return out;
}

/** Whole sentences for a live lane's box. */
export function laneStory(lane: SetupLane): { title: string; lines: string[] } {
  if (isFlatTop(lane.setup_type)) return flatTopStory(lane);
  const lines = [lane.reason || lane.state];
  const short = isShortEpisode(lane);
  if (lane.leg) {
    lines.push(short ? shortLegLine(lane.setup_type, lane.leg)
      : `Leg ${lane.leg.pct >= 0 ? '+' : ''}${(lane.leg.pct * 100).toFixed(1)}% to ${fmtPx(lane.leg.high)}`);
  }
  const lv = lane.setup ?? lane.forming;
  if (lv) {
    lines.push(short ? shortArmedLine(lv, Boolean(lane.setup))
      : `${lane.setup ? 'Armed' : 'Would arm'}: trigger ${fmtPx(lv.trigger)}, stop ${fmtPx(lv.stop)}, target ${fmtPx(lv.target1)}`);
  }
  if (lane.state === 'failed') lines.push('It stays here faint once the lane moves on, with what price did next.');
  return { title: `${setupName(lane.setup_type)} · ${lane.state}`, lines };
}

/** The legend chip's count: past setups drawn, by how they ended. */
export function pastCounts(episodes: Episode[]): { failed: number; faded: number; triggered: number } {
  return {
    failed: episodes.filter(e => endOf(e) === 'failed').length,
    faded: episodes.filter(e => endOf(e) === 'faded').length,
    triggered: episodes.filter(e => endOf(e) === 'triggered').length,
  };
}
