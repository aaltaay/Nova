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
  return async (url: string, init?: RequestInit): Promise<Json> => {
    const href = String(url);
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
    if (href.includes('/bot/proposals/')) return ok({});
    if (href.includes('/bot/proposals')) return ok({ proposals: opts.proposals ?? [] });
    if (href.includes('/bot/audit')) return ok({ entries: opts.audit ?? [] });
    if (href.includes('/bot/pnl')) return ok({ day_pnl: opts.dayPnl ?? null, meter: {} });
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
