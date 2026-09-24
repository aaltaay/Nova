/** Wire -> types for the stock read (ADR 036). A field the wire lacks or mistypes is dropped or null
 * -- never guessed; a payload that is not a read is null. */
import type {
  DailyBar,
  DecisionEvent,
  FormingLevels,
  LaneSeries,
  PlanCheck,
  PlanMark,
  ReadGroup,
  ReadGroupId,
  ReadRow,
  ReadState,
  RunDay,
  SetupLane,
  SetupLeg,
  SetupLevels,
  SetupWindow,
  SplitFact,
  StockDecisions,
  StockHistory,
  StockPlan,
  StockRead,
  TapeVerdict,
} from './types';

const STATES: ReadonlySet<string> = new Set<ReadState>(['ok', 'warn', 'bad', 'unknown', 'info']);
const GROUPS: ReadonlySet<string> = new Set<ReadGroupId>([
  'in_play', 'setups', 'front', 'tape', 'short', 'float', 'halts',
]);
const MARK_KINDS: ReadonlySet<string> = new Set(['hod', 'vwap', 'pmh', 'round', 'wall', 'open']);
const PLAN_STATES: ReadonlySet<string> = new Set(['forming', 'armed', 'near', 'triggered', 'manual']);

type Obj = Record<string, unknown>;

function obj(v: unknown): Obj | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null;
}

export function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' ? v : null;
}

function list<T>(v: unknown, fn: (x: unknown) => T | null): T[] {
  return Array.isArray(v) ? v.map(fn).filter((x): x is T => x !== null) : [];
}

function state(v: unknown): ReadState {
  return typeof v === 'string' && STATES.has(v) ? (v as ReadState) : 'unknown';
}

export function normalizeRow(raw: unknown): ReadRow | null {
  const r = obj(raw);
  if (!r || typeof r.id !== 'string' || typeof r.label !== 'string') return null;
  return {
    id: r.id,
    label: r.label,
    value: str(r.value) ?? '',
    detail: str(r.detail),
    state: state(r.state),
    source: str(r.source) ?? '',
    as_of: num(r.as_of),
  };
}

function group(raw: unknown): ReadGroup | null {
  const g = obj(raw);
  if (!g || typeof g.id !== 'string' || !GROUPS.has(g.id)) return null;
  return {
    id: g.id as ReadGroupId,
    label: str(g.label) ?? g.id,
    question: str(g.question) ?? '',
    verdict: state(g.verdict),
    value: str(g.value) ?? '',
    rows: list(g.rows, normalizeRow),
  };
}

function check(raw: unknown): PlanCheck | null {
  const c = obj(raw);
  return c && typeof c.id === 'string' && typeof c.text === 'string'
    ? { id: c.id, state: state(c.state), text: c.text }
    : null;
}

function mark(raw: unknown): PlanMark | null {
  const m = obj(raw);
  const price = num(m?.price);
  if (!m || price === null || typeof m.label !== 'string') return null;
  const kind = typeof m.kind === 'string' && MARK_KINDS.has(m.kind) ? m.kind : 'round';
  return { price, label: m.label, kind: kind as PlanMark['kind'], size: num(m.size) };
}

function tape(v: unknown): TapeVerdict | null {
  const t = obj(v);
  if (!t || typeof t.verdict !== 'string') return null;
  return { verdict: t.verdict, reasons: list(t.reasons, x => (typeof x === 'string' ? x : null)) };
}

function windowOf(v: unknown): SetupWindow | null {
  const w = obj(v);
  return w && typeof w.start === 'string' && typeof w.end === 'string'
    ? { start: w.start, end: w.end, state: str(w.state) ?? '' }
    : null;
}

export function normalizePlan(raw: unknown): StockPlan | null {
  const p = obj(raw);
  if (!p || (p.source !== 'setup' && p.source !== 'manual')) return null;
  const flow = obj(p.flow);
  return {
    source: p.source,
    setup_type: str(p.setup_type),
    kind: str(p.kind),
    state: (typeof p.state === 'string' && PLAN_STATES.has(p.state) ? p.state : 'forming') as StockPlan['state'],
    provisional: p.provisional === true,
    trigger: num(p.trigger),
    entry: num(p.entry),
    stop: num(p.stop),
    target: num(p.target),
    risk: num(p.risk),
    reward: num(p.reward),
    rr: num(p.rr),
    target_rule: str(p.target_rule) ?? '',
    entry_rule: str(p.entry_rule) ?? '',
    stop_rule: str(p.stop_rule) ?? '',
    grade: str(p.grade),
    reason: str(p.reason) ?? '',
    tape: tape(p.tape),
    flow: flow && typeof flow.label === 'string' ? { score: num(flow.score), label: flow.label } : null,
    window: windowOf(p.window),
    checks: list(p.checks, check),
    marks: list(p.marks, mark),
  };
}

/** An armed (or triggered) setup's levels; null unless trigger, entry, stop and target are numbers. */
export function normalizeSetupLevels(raw: unknown): SetupLevels | null {
  const s = obj(raw);
  const trigger = num(s?.trigger);
  const entry = num(s?.entry);
  const stop = num(s?.stop);
  const target1 = num(s?.target1);
  if (!s || trigger === null || entry === null || stop === null || target1 === null) return null;
  return {
    trigger,
    entry,
    stop,
    risk: num(s.risk) ?? entry - stop,
    target1,
    leg_t: num(s.leg_t) ?? undefined,
    leg_high: num(s.leg_high) ?? undefined,
    leg_low: num(s.leg_low) ?? undefined,
    pullback_bars: num(s.pullback_bars) ?? undefined,
    armed_bar_t: num(s.armed_bar_t) ?? undefined,
    triggered_at: num(s.triggered_at) ?? undefined,
    trigger_price: num(s.trigger_price) ?? undefined,
    detail: obj(s.detail),
  };
}

function forming(raw: unknown): FormingLevels | null {
  const f = obj(raw);
  const trigger = num(f?.trigger);
  const entry = num(f?.entry);
  const stop = num(f?.stop);
  const target1 = num(f?.target1);
  if (!f || trigger === null || entry === null || stop === null || target1 === null) return null;
  return {
    trigger,
    entry,
    stop,
    risk: num(f.risk) ?? entry - stop,
    target1,
    bars: num(f.bars) ?? 0,
    blocked: str(f.blocked),
    waiting: str(f.waiting),
  };
}

export function normalizeLeg(raw: unknown): SetupLeg | null {
  const l = obj(raw);
  const t = num(l?.t);
  const high = num(l?.high);
  const low = num(l?.low);
  if (!l || t === null || high === null || low === null) return null;
  return { t, high, low, pct: num(l.pct) ?? 0, bars: num(l.bars) ?? undefined };
}

function series(raw: unknown): LaneSeries | null {
  const s = obj(raw);
  const hist = num(s?.macd_hist);
  if (!s || hist === null) return null;
  return {
    bars_as_of: num(s.bars_as_of) ?? 0,
    close: num(s.close) ?? 0,
    ema: num(s.ema) ?? 0,
    macd_line: num(s.macd_line) ?? 0,
    macd_signal: num(s.macd_signal) ?? 0,
    macd_hist: hist,
    hod: num(s.hod) ?? 0,
  };
}

function lane(raw: unknown): SetupLane | null {
  const l = obj(raw);
  if (!l || typeof l.setup_type !== 'string' || typeof l.state !== 'string') return null;
  return {
    setup_type: l.setup_type,
    state: l.state,
    reason: str(l.reason) ?? '',
    kind: str(l.kind),
    chosen: l.chosen === true,
    level: num(l.level) ?? 0,
    setup: normalizeSetupLevels(l.setup),
    forming: forming(l.forming),
    leg: normalizeLeg(l.leg),
    last_price: num(l.last_price),
    distance: num(l.distance),
    grade: str(l.grade),
    tape: tape(l.tape),
    window: windowOf(l.window),
    series: series(l.series),
  };
}

/** The read off the wire; null when it is not one. */
export function normalizeStockRead(raw: unknown): StockRead | null {
  const r = obj(raw);
  if (!r || typeof r.symbol !== 'string' || !Array.isArray(r.groups)) return null;
  const lv = obj(r.levels) ?? {};
  const hod = obj(lv.hod);
  const hodPrice = num(hod?.price);
  const counts = obj(r.counts) ?? {};
  return {
    schema_version: num(r.schema_version) ?? 0,
    symbol: r.symbol,
    generated_at: num(r.generated_at) ?? 0,
    session_date: str(r.session_date) ?? '',
    price: num(r.price),
    prev_close: num(r.prev_close),
    change_pct: num(r.change_pct),
    followed: r.followed === true,
    followed_note: str(r.followed_note),
    setups: list(r.setups, lane),
    no_scanner: list(r.no_scanner, x => {
      const o = obj(x);
      return o && typeof o.setup_type === 'string'
        ? { setup_type: o.setup_type, label: str(o.label) ?? o.setup_type, reason: str(o.reason) ?? '' }
        : null;
    }),
    plan: normalizePlan(r.plan),
    levels: {
      hod: hodPrice !== null ? { price: hodPrice, ts: num(hod?.ts) ?? 0 } : null,
      pmh: num(lv.pmh),
      open: num(lv.open),
      prev_close: num(lv.prev_close),
      vwap: num(lv.vwap),
      round_above: num(lv.round_above),
      round_below: num(lv.round_below),
    },
    groups: list(r.groups, group),
    counts: {
      ok: num(counts.ok) ?? 0,
      warn: num(counts.warn) ?? 0,
      bad: num(counts.bad) ?? 0,
      unknown: num(counts.unknown) ?? 0,
      info: num(counts.info) ?? 0,
    },
  };
}

function decisionEvent(raw: unknown): DecisionEvent | null {
  const e = obj(raw);
  const ts = num(e?.ts);
  if (!e || ts === null || typeof e.title !== 'string') return null;
  const lv = obj(e.levels);
  const leg = lv ? normalizeLeg(lv.leg) : null;
  const setup = lv ? normalizeSetupLevels(lv.setup) : null;
  return {
    ts,
    lane: str(e.lane) ?? 'market',
    event: str(e.event) ?? '',
    title: e.title,
    detail: str(e.detail),
    count: num(e.count) ?? 1,
    last_ts: num(e.last_ts),
    levels: leg || setup ? { leg, setup } : null,
  };
}

export function normalizeDecisions(raw: unknown): StockDecisions | null {
  const r = obj(raw);
  const s = obj(r?.summary);
  if (!r || !s || typeof r.symbol !== 'string' || !Array.isArray(r.events)) return null;
  const sources: StockDecisions['sources'] = {};
  for (const [k, v] of Object.entries(obj(r.sources) ?? {})) {
    const o = obj(v);
    if (o) sources[k] = { ok: o.ok === true, error: str(o.error) };
  }
  return {
    symbol: r.symbol,
    date: str(r.date) ?? '',
    summary: {
      text: str(s.text) ?? '',
      legs: num(s.legs) ?? 0,
      armed: num(s.armed) ?? 0,
      near: num(s.near) ?? 0,
      triggered: num(s.triggered) ?? 0,
      trades: num(s.trades) ?? 0,
      refusals: list(s.refusals, x => {
        const o = obj(x);
        return o && typeof o.reason === 'string' ? { reason: o.reason, count: num(o.count) ?? 1 } : null;
      }),
    },
    events: list(r.events, decisionEvent),
    sources,
  };
}

function dailyBar(raw: unknown): DailyBar | null {
  const b = obj(raw);
  const o = num(b?.o);
  const h = num(b?.h);
  const l = num(b?.l);
  const c = num(b?.c);
  if (!b || typeof b.d !== 'string' || o === null || h === null || l === null || c === null) return null;
  return { d: b.d, o, h, l, c, v: num(b.v) ?? 0 };
}

function runDay(raw: unknown): RunDay | null {
  const x = obj(raw);
  const prior = num(x?.prior_close);
  const high = num(x?.high);
  const close = num(x?.close);
  const run = num(x?.run_pct);
  if (!x || typeof x.date !== 'string' || prior === null || high === null || close === null || run === null) {
    return null;
  }
  return {
    date: x.date,
    prior_close: prior,
    high,
    close,
    run_pct: run,
    close_pct: num(x.close_pct) ?? close / prior - 1,
    today: x.today === true,
  };
}

function split(raw: unknown): SplitFact | null {
  const s = obj(raw);
  if (!s) return null;
  return {
    factor: str(s.factor),
    ts: num(s.ts),
    reverse: typeof s.reverse === 'boolean' ? s.reverse : null,
    days_ago: num(s.days_ago),
  };
}

export function normalizeHistory(raw: unknown): StockHistory | null {
  const r = obj(raw);
  if (!r || typeof r.symbol !== 'string') return null;
  return {
    symbol: r.symbol,
    daily: list(r.daily, dailyBar),
    runs: list(r.runs, runDay),
    split: split(r.split),
    holdings: list(r.holdings, normalizeRow),
  };
}
