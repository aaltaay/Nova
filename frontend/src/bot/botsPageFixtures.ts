/**
 * Test data for the Bots page tests (approved mockup v4, ADR 042): a session in the
 * wire contract's shape -- the master level, a level per setup, Activate and why it
 * was cleared, the gates in two stages, the sleeve per venue, today's Nova entries, the
 * day lock and the bot trip -- and a fetch router that answers every endpoint the page
 * reads. Pure data -- the tests wrap `botsFetchRouter` in their own mock.
 */
import type { SetupStoreRow } from '../setups/useSetupRows';
import templatesFixture from './setupTemplatesFixture.json';
import type { TemplatesPayload } from './templateTypes';
import type { BotAuditEntry, BotBreakers, BotCaps, BotGate, BotProposal, BotSession } from './types';

/** The backend's own GET /api/setups/templates (default templates only), a fresh copy each call. */
export function templatesPayload(): TemplatesPayload {
  return JSON.parse(JSON.stringify(templatesFixture)) as TemplatesPayload;
}

/** The gates on Paper with the master level at Eyes and the first pullback's own switch at Strategy. */
export function gates(overrides: Partial<Record<string, Partial<BotGate>>> = {}): BotGate[] {
  const base: BotGate[] = [
    { id: 'venue', ok: true, stage: 'activate', detail: { venue: 'paper', live_edge: false, text: null } },
    { id: 'level', ok: false, stage: 'activate', detail: { level: 1 } },
    { id: 'setups', ok: false, stage: 'activate', detail: { at_strategy: [] } },
    { id: 'padlock', ok: true, stage: 'activate', detail: { reason: null } },
    { id: 'allowlist', ok: true, stage: 'fire', detail: { count: 2, auto_entry: 0 } },
    { id: 'bot_trip', ok: true, stage: 'activate', detail: { fired_at: null, pnl: null, until: null } },
    { id: 'depth_lines', ok: true, stage: 'fire', detail: { held: ['GRML'], missing: ['IMCC'], max_lines: 3 } },
    { id: 'day_lock', ok: true, stage: 'fire', detail: { until: null, tripped_at: null, pnl: null, venue: 'paper' } },
    { id: 'kill_switch', ok: true, stage: 'fire', detail: {} },
    { id: 'window', ok: true, stage: 'fire', detail: { setups: [], venue_time: null } },
    { id: 'daily_cap', ok: true, stage: 'fire', detail: { count: 0, cap: 1, venue_day: '2026-09-30' } },
    { id: 'extended_hours', ok: true, stage: 'fire', detail: {} },
    { id: 'commissions', ok: true, stage: 'fire', detail: {} },
  ];
  return base.map(g => ({ ...g, ...(overrides[g.id] ?? {}) }));
}

/** The gates with every Activate gate open: Strategy, the first pullback at Strategy, inside its window. */
export function openGates(overrides: Partial<Record<string, Partial<BotGate>>> = {}): BotGate[] {
  return gates({
    level: { ok: true, detail: { level: 2 } },
    setups: { ok: true, detail: { at_strategy: ['first_pullback'] } },
    window: { ok: true, detail: { setups: [{ setup: 'first_pullback', start: '07:00', end: '10:00', open: true, clipped: false }], venue_time: null } },
    ...overrides,
  });
}

/** The loss breakers a session answers (ADR 032): the desk venue's pair, every venue's, the bounds. */
export function breakers(partial: Partial<BotBreakers> = {}): BotBreakers {
  const pair = { soft_usd: -50, hard_usd: -200 };
  return {
    venue: 'paper', ...pair, custom: false, defaults: { ...pair },
    by_venue: { live: { ...pair }, paper: { ...pair }, sim: { ...pair } },
    bounds: { soft_usd: [-1000, -5], hard_usd: [-5000, -10], step_usd: 5 },
    note: null,
    ...partial,
  };
}

/** One venue's sleeve (ADR 042 E). */
export function caps(venue = 'paper', partial: Partial<BotCaps> = {}): BotCaps {
  return {
    venue, risk_usd: 20, max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false,
    entries_per_day: 1, api_kinds: [], allowlist: [], ...partial,
  };
}

export function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 1, active: false, armed: false, has_desk_arm: false, deactivated: null,
    // ADR 042: four setups with a scanner, each with its own level; the master caps them.
    setups: [
      { id: 'first_pullback', scanner: true, level: 2, effective: 1 },
      { id: 'bull_flag', scanner: true, level: 1, effective: 1 },
      { id: 'flat_top_breakout', scanner: true, level: 0, effective: 0 },
      { id: 'red_to_green', scanner: true, level: 0, effective: 0 },
      { id: 'gap_and_go', scanner: false, level: null, effective: null },
      { id: 'micro_pullback', scanner: false, level: null, effective: null },
    ],
    setup_levels: { first_pullback: 2, bull_flag: 1, flat_top_breakout: 0, red_to_green: 0 },
    ready: false, ready_reason: null, live_fire_ready: false,
    breakers: breakers(),
    gates: gates(),
    symbol_allowlist: ['GRML', 'IMCC'],
    brain_session_id: null, brain_alive: false,
    caps: caps('paper'),
    caps_bounds: { risk_usd: [1, 10000], max_shares: [1, 10], bp_budget_usd: [0.01, 50], working_ttl_sec: [1, 10], entries_per_day: [1, 3] },
    caps_by_venue: { paper: caps('paper'), sim: caps('sim'), live: caps('live') },
    entries_today: { count: 0, cap: 1, venue_day: '2026-09-30', entries: [], approved: 0 },
    day_lock: { active: false, until: null, tripped_at: null, pnl: null, venue: 'paper' },
    soft_breaker: { fired: false, at: null, pnl: null, until: null },
    soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false,
    level_venue: 'paper',
    focus: [], trader_live: [], working: [],
    ...partial,
  };
}

/** A session at Strategy with every Activate gate open and the first pullback at effective Strategy. */
export function strategySession(partial: Partial<BotSession> = {}): BotSession {
  return session({
    level: 2,
    setups: [
      { id: 'first_pullback', scanner: true, level: 2, effective: 2 },
      { id: 'bull_flag', scanner: true, level: 1, effective: 1 },
      { id: 'flat_top_breakout', scanner: true, level: 0, effective: 0 },
      { id: 'red_to_green', scanner: true, level: 0, effective: 0 },
      { id: 'gap_and_go', scanner: false, level: null, effective: null },
      { id: 'micro_pullback', scanner: false, level: null, effective: null },
    ],
    gates: openGates(),
    ...partial,
  });
}

export function setupRow(partial: Partial<SetupStoreRow> = {}): SetupStoreRow {
  return {
    id: 'GRML-2026-09-22-1', session_date: '2026-09-22', symbol: 'GRML', kind: 'first_pullback', state: 'near',
    reason: '', armed_at: 1_790_000_000, trigger: 8.72, entry_planned: 8.73, stop: 8.52, target1: 8.92,
    leg_pct: 0.074, pullback_bars: 2, grade: 'A', near_at: null, near_tape: null, triggered_at: null, entry: null,
    trigger_tape: null, failed_at: null, fail_reason: null, disarmed_at: null, outcome: null, outcome_at: null,
    bar_r: null,
    ...partial,
  };
}

type Json = { ok: boolean; status: number; json: () => Promise<unknown> };
export type PatchAnswer = BotSession | Json;

export interface BotsFetchOpts {
  session?: BotSession;
  proposals?: BotProposal[];
  audit?: BotAuditEntry[];
  setupRows?: SetupStoreRow[];
  dayPnl?: number | null;
  killTripped?: boolean;
  /** The kill switch trip's answer (ADR 042 D): its sweep per venue. */
  killSweep?: unknown;
  /** `GET /api/stock-mode`'s stocks, or a failing answer. */
  stockModes?: unknown[] | Json;
  onPatch?: (body: Record<string, unknown>) => PatchAnswer | undefined;
  onArm?: (body: Record<string, unknown>) => BotSession | Json;
  onDisarm?: () => BotSession;
  onAllowlist?: (body: { symbol: string; op: string }) => BotSession | Json;
  templates?: TemplatesPayload;
  onTemplate?: (method: string, href: string, body: Record<string, unknown>) => Json | undefined;
  /** `POST /api/bot/session/switch` (ADR 043): the session after it, or a refusal. */
  onSwitch?: (body: Record<string, unknown>) => BotSession | Json;
  /** `GET /api/bot/triggers`: Tickers today and the answer line read it. */
  triggers?: unknown;
  /** `GET /api/hot-list`; a write answers `onHotList` (else the same view). */
  hotList?: unknown;
  onHotList?: (method: string, href: string, body: Record<string, unknown>) => Json | undefined;
  /** `GET /api/ibkr/depth/lines`; `PATCH /api/ibkr/depth/lending` flips `lending.on`. */
  lines?: unknown;
  /** `PUT /api/stock-mode/{symbol}`: the stock's view after it (default: the switch as sent), or a refusal. */
  onStockModePut?: (symbol: string, body: Record<string, unknown>) => Json | undefined;
}

const MODE_OF: Record<string, string> = { 'you/you': 'signal', 'nova/you': 'auto_entry', 'you/nova': 'approve', 'nova/nova': 'bot' };

/** One stock's Who trades view (`GET /api/stock-mode/{symbol}`), in the wire's shape. */
export function stockModeView(symbol: string, buy: string, sell: string, partial: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1, symbol, generated_at: 0, venue: 'paper', mode: MODE_OF[`${buy}/${sell}`] ?? 'signal', buy, sell,
    risk_usd: 20, set_at: 0, locks: { buy: null, sell: null }, notes: [], approval: null, trade: null,
    entries_today: { count: 0, cap: 1 }, last_event: null, bot: null, size: null, ...partial,
  };
}

/** Today's squares by ticker: GRML on the hot list (Buy Nova), one trigger stopped by its tape; IMCC not listed. */
export function triggersView(partial: Record<string, unknown> = {}): Record<string, unknown> {
  const gate = (id: string, label: string) => ({ id, label });
  const cell = (ok: boolean | null, why = '') => ({ ok, why });
  const allOk = {
    bot_on: cell(true), strategy_on: cell(true), grade: cell(true), setups_a_day: cell(true), bot_window: cell(true),
    hot_list: cell(true), nova_buys: cell(true), level2_line: cell(true), tape_go: cell(true), trades_today: cell(true),
  };
  return {
    schema_version: 1, date: '2026-10-01', generated_at: 0,
    gates: [
      gate('bot_on', 'Bot on'), gate('strategy_on', 'Strategy on'), gate('grade', 'Grade'),
      gate('setups_a_day', 'Setups a day'), gate('bot_window', 'Bot window'), gate('hot_list', 'Hot list'),
      gate('nova_buys', 'Nova buys'), gate('level2_line', 'Level 2 line'), gate('tape_go', 'Tape GO'),
      gate('trades_today', 'Trades today'),
    ],
    tickers: [
      { symbol: 'GRML', listed: { how: 'auto', at: 1_790_000_000 },
        now: { cells: { ...allOk, bot_window: cell(false, 'the bot window 07:00–10:00 closed') }, answer: 'no',
          reasons: ['the bot window 07:00–10:00 closed'] },
        triggers: [{ ts: 1_790_000_600, setup_id: 'g1', setup_type: 'first_pullback', kind: 'first_pullback', nth: 1,
          grade: 'A', tape: 'blind', outcome: 'target_first', r: 1.6,
          cells: { ...allOk, level2_line: cell(false, 'no Level 2 line: the tape was BLIND'), tape_go: cell(null, 'no tape to read') },
          reasons: ['no Level 2 line: the tape was BLIND'] }] },
      { symbol: 'IMCC', listed: null, now: null,
        triggers: [{ ts: 1_790_001_200, setup_id: 'i1', setup_type: 'bull_flag', kind: 'bull_flag', nth: 1, grade: 'B',
          tape: 'wait', outcome: 'stop_first', r: -1, cells: { ...allOk, hot_list: cell(false, 'not on the hot list') },
          reasons: ['not on the hot list'] }] },
    ],
    impact: [{ gate: 'level2_line', blocked: 1, target_first: 1, stop_first: 0, r: 1.6 }],
    judged_now: [],
    sources: { journal: { ok: true, error: null } },
    ...partial,
  };
}

/** Today's hot list: GRML put on by the auto top 5 at 07:12. */
export function hotListView(partial: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1, date: '2026-10-01', cap: 20,
    auto: { n: 5, start: '07:00', end: '16:00', rule: 'leaders', error: null },
    default: { buy: 'you', sell: 'you' },
    entries: [{ symbol: 'GRML', how: 'auto', at: 1_790_000_000, board: 'gainers', rank: 1, change_pct: 0.42, followed: true }],
    yesterday: [], error: null,
    ...partial,
  };
}

/** IBKR's three Level 2 lines: GRML in front, a free line, a Record; lending on. */
export function linesView(partial: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1, cap: 3,
    lines: [
      { symbol: 'GRML', held_by: 'tab', front: true, viewers: 1 },
      { symbol: 'NXL', held_by: 'tab', front: false, viewers: 1 },
    ],
    lending: { on: true, loans: [], recent: [] },
    ...partial,
  };
}

const ok = (body: unknown): Json => ({ ok: true, status: 200, json: async () => body });
const isJson = (v: unknown): v is Json => v != null && typeof v === 'object' && 'ok' in v && 'json' in v;

/** A refusal in the backend's own shape: `{detail: {reason, error}}`. */
export function refusal(status: number, reason: string, error: string): Json {
  return { ok: false, status, json: async () => ({ detail: { reason, error } }) };
}

/** One answer per endpoint the Bots page reads or writes; anything else is `{}`. */
export function botsFetchRouter(opts: BotsFetchOpts = {}) {
  let current = opts.session ?? session();
  let tripped = opts.killTripped ?? false;
  let lines = (opts.lines ?? linesView()) as Record<string, unknown>;
  return async (url: string, init?: RequestInit): Promise<Json> => {
    const href = String(url);
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
    if (href.includes('/bot/triggers')) return ok(opts.triggers ?? triggersView());
    if (href.includes('/hot-list')) {
      const answer = method === 'GET' ? undefined : opts.onHotList?.(method, href, body);
      return answer ?? ok(opts.hotList ?? hotListView());
    }
    if (href.includes('/ibkr/depth/lending')) {
      lines = { ...lines, lending: { ...(lines.lending as object), on: body.on === true } };
      return ok(lines);
    }
    if (href.includes('/ibkr/depth/lines')) return ok(lines);
    if (href.includes('/session/switch')) {
      const on = body.on === true;
      const next = opts.onSwitch?.(body) ?? { ...current, bot_on: on, active: on, armed: on, level: on ? 2 : 1,
        has_desk_arm: on, deactivated: null, ...(on ? { desk_arm_token: 'desk-token-1' } : {}) };
      if (isJson(next)) return next;
      current = next;
      return ok(current);
    }
    if (href.includes('/bot/proposals/')) return ok({});
    if (href.includes('/bot/proposals')) return ok({ proposals: opts.proposals ?? [] });
    if (href.includes('/bot/audit')) return ok({ entries: opts.audit ?? [] });
    if (href.includes('/bot/pnl')) return ok({ day_pnl: opts.dayPnl ?? null, meter: {} });
    if (href.includes('/stock-mode/') && method === 'PUT') {
      const symbol = decodeURIComponent(href.split('/stock-mode/')[1] ?? '').split('?')[0];
      return opts.onStockModePut?.(symbol, body) ?? ok(stockModeView(symbol, String(body.buy), String(body.sell)));
    }
    if (href.includes('/stock-mode')) {
      if (isJson(opts.stockModes)) return opts.stockModes;
      return ok({ schema_version: 1, generated_at: 0, venue: 'paper', stocks: opts.stockModes ?? [] });
    }
    if (href.includes('/kill-switch')) {
      if (method === 'POST') tripped = !href.endsWith('/reset');
      const sweep = method === 'POST' && tripped ? { sweep: opts.killSweep ?? [] } : {};
      return ok({ tripped, reason: null, ts: null, ...sweep });
    }
    if (href.includes('/setups/templates')) {
      const answer = method === 'GET' ? undefined : opts.onTemplate?.(method, href, body);
      if (answer) return answer;
      return ok(opts.templates ?? templatesPayload());
    }
    if (href.includes('/setups/rows')) return ok({ date: '2026-09-22', rows: opts.setupRows ?? [] });
    if (href.includes('/setups/scoreboard')) {
      return ok({ days: 5, date_from: null, row_count: 0, rows: [], summary: {
        all: { armed: 6, triggered: 2 },
        by: { tape_at_trigger: {
          go: { triggered: 12, win_pct: 58, avg_net_r: 0.31 },
          wait: { triggered: 9, win_pct: 38, avg_net_r: -0.12 },
          blind: { triggered: 31, win_pct: 27, avg_net_r: -0.24 },
        } },
      } });
    }
    if (href.includes('/session/arm')) {
      const next = opts.onArm?.(body) ?? { ...current, active: true, armed: true, has_desk_arm: true, deactivated: null, desk_arm_token: 'desk-token-1' };
      if (isJson(next)) return next;
      current = next;
      return ok(current);
    }
    if (href.includes('/session/disarm')) {
      current = opts.onDisarm?.() ?? { ...current, active: false, armed: false, has_desk_arm: false };
      return ok(current);
    }
    if (href.includes('/bot/allowlist') && method === 'POST') {
      const next = opts.onAllowlist?.(body as { symbol: string; op: string }) ?? current;
      if (isJson(next)) return next;
      current = next;
      return ok(current);
    }
    if (href.includes('/bot/session') && method === 'PATCH') {
      const next = opts.onPatch?.(body);
      if (next && isJson(next) && next.ok === false) return next;
      if (next && !isJson(next)) current = next;
      return ok(current);
    }
    if (href.includes('/bot/session')) return ok(current);
    return ok({});
  };
}
