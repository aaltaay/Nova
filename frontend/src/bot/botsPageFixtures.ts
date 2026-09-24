/**
 * Test data for the Bots page tests (approved mockup v4): a session with the
 * nine gates, the read-out, and a fetch router that answers every endpoint the
 * page reads. Pure data -- the tests wrap `botsFetchRouter` in their own mock.
 */
import type { SetupStoreRow } from '../setups/useSetupRows';
import templatesFixture from './setupTemplatesFixture.json';
import type { TemplatesPayload } from './templateTypes';
import type { BotAuditEntry, BotBreakers, BotGate, BotProposal, BotSession } from './types';

/** The backend's own GET /api/setups/templates (default templates only), a fresh copy each call. */
export function templatesPayload(): TemplatesPayload {
  return JSON.parse(JSON.stringify(templatesFixture)) as TemplatesPayload;
}

export const CLOSED_READOUT = {
  state: 'collecting', passed: false, reason: '12 of 50 go setups triggered',
  go: { triggered: 12, scored: 12, win_pct: 58, avg_net_r: 0.31 },
  control: { triggered: 40, scored: 40, win_pct: 27, avg_net_r: -0.18 },
  rules: { kind: 'first_pullback', min_go: 50, fail_go: 100, min_net_r: 0.2 },
};

export function gates(overrides: Partial<Record<string, Partial<BotGate>>> = {}): BotGate[] {
  const base: BotGate[] = [
    { id: 'level', ok: false, stage: 'activate', detail: { level: 1 } },
    { id: 'allowlist', ok: true, stage: 'activate', detail: { count: 2 } },
    { id: 'desk_armed', ok: true, stage: 'activate', detail: {} },
    { id: 'depth_lines', ok: false, stage: 'fire', detail: { held: ['GRML'], missing: ['IMCC'] } },
    { id: 'readout', ok: false, stage: 'activate', detail: { state: 'collecting', go_triggered: 12, min_go: 50 } },
    { id: 'bot_trip', ok: true, stage: 'activate', detail: {} },
    { id: 'day_lock', ok: true, stage: 'fire', detail: {} },
    { id: 'kill_switch', ok: true, stage: 'fire', detail: {} },
    { id: 'window', ok: true, stage: 'fire', detail: { start: '07:00', end: '10:00', open: true, entries_today: 0, max_entries: 1 } },
  ];
  return base.map(g => ({ ...g, ...(overrides[g.id] ?? {}) }));
}

/** The loss breakers a session answers (ADR 032): the desk venue's pair, every venue's, the bounds. */
export function breakers(partial: Partial<BotBreakers> = {}): BotBreakers {
  const pair = { soft_usd: -50, hard_usd: -200 };
  return {
    venue: 'paper', ...pair, custom: false, defaults: { ...pair },
    by_venue: { live: { ...pair }, paper: { ...pair }, sim: { ...pair } },
    bounds: { soft_usd: [-1000, -5], hard_usd: [-5000, -10], step_usd: 5 },
    ...partial,
  };
}

export function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 1, armed: false, has_desk_arm: false, strategy: null,
    setup: 'first_pullback',
    // ADR 031: four setups with a scanner, each with its own level; two waiting on theirs.
    setups: [
      { id: 'first_pullback', scanner: true, level: 1 }, { id: 'bull_flag', scanner: true, level: 0 },
      { id: 'flat_top_breakout', scanner: true, level: 0 }, { id: 'red_to_green', scanner: true, level: 0 },
      { id: 'gap_and_go', scanner: false, level: null }, { id: 'micro_pullback', scanner: false, level: null },
    ],
    setup_levels: { bull_flag: 0, flat_top_breakout: 0, red_to_green: 0 },
    breakers: breakers(),
    readout: CLOSED_READOUT,
    gates: gates(),
    symbol_allowlist: ['GRML', 'IMCC'],
    brain_session_id: null, brain_alive: false, live_fire_ready: false,
    caps: { max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false, allowlist: [] },
    advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
    soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false,
    focus: [], trader_live: [], working: [],
    ...partial,
  };
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
  onPatch?: (body: Record<string, unknown>) => PatchAnswer | undefined;
  onArm?: () => BotSession;
  onDisarm?: () => BotSession;
  onAllowlist?: (body: { symbol: string; op: string }) => BotSession;
  templates?: TemplatesPayload;
  onTemplate?: (method: string, href: string, body: Record<string, unknown>) => Json | undefined;
}

const ok = (body: unknown): Json => ({ ok: true, status: 200, json: async () => body });

/** One answer per endpoint the Bots page reads or writes; anything else is `{}`. */
export function botsFetchRouter(opts: BotsFetchOpts = {}) {
  let current = opts.session ?? session();
  let tripped = opts.killTripped ?? false;
  return async (url: string, init?: RequestInit): Promise<Json> => {
    const href = String(url);
    const method = init?.method ?? 'GET';
    if (href.includes('/bot/proposals/')) return ok({});
    if (href.includes('/bot/proposals')) return ok({ proposals: opts.proposals ?? [] });
    if (href.includes('/bot/audit')) return ok({ entries: opts.audit ?? [] });
    if (href.includes('/bot/pnl')) return ok({ day_pnl: opts.dayPnl ?? null, meter: {} });
    if (href.includes('/kill-switch')) {
      if (method === 'POST') tripped = !href.endsWith('/reset');
      return ok({ tripped, reason: null, ts: null });
    }
    if (href.includes('/setups/templates')) {
      const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
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
      current = opts.onArm?.() ?? { ...current, armed: true, has_desk_arm: true, desk_arm_token: 'desk-token-1' };
      return ok(current);
    }
    if (href.includes('/session/disarm')) {
      current = opts.onDisarm?.() ?? { ...current, armed: false, has_desk_arm: false };
      return ok(current);
    }
    if (href.includes('/bot/allowlist') && method === 'POST') {
      const body = JSON.parse(String(init?.body || '{}')) as { symbol: string; op: string };
      current = opts.onAllowlist?.(body) ?? current;
      return ok(current);
    }
    if (href.includes('/bot/session') && method === 'PATCH') {
      const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
      const next = opts.onPatch?.(body);
      if (next && 'ok' in next && next.ok === false) return next as Json;
      if (next) current = next as BotSession;
      return ok(current);
    }
    if (href.includes('/bot/session')) return ok(current);
    return ok({});
  };
}
