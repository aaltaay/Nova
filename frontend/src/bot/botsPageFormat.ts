/** Pure helpers for the Bots page (ADR 027): gate chips, the headline, read-out numbers. */
import {
  BOT_GATE_LABELS,
  BOT_LEVEL_LABELS,
  BOT_SETUP_LABELS,
  BOT_SOFT_BREAKER_USD,
  BOT_STRATEGY_NOT_BUILT,
} from '../constantGroups/bot';
import {
  BOTS_GATE_ADD_SYMBOL,
  BOTS_GATE_OPEN_L2,
  BOTS_GATE_READOUT_LINK,
  BOTS_GATE_RESET_KILL,
  BOTS_GATE_UNLOCK,
  BOTS_HERO_NO_GATES,
} from '../constantGroups/bots_page';
import type { TradingBlocker } from '../ibkr/tradingAllowed';
import type { BotGate, BotReadout, BotSession } from './types';

/** How many missing depth lines a chip names before "+N more". */
const OPEN_L2_NAMED = 2;

export type GateActionKind = 'unlock' | 'open_l2' | 'readout' | 'add_symbol' | 'reset_kill';

export interface GateAction {
  kind: GateActionKind;
  label: string;
  symbol?: string;
}

export interface GateLine {
  id: string;
  ok: boolean;
  stage: string;
  text: string;
  actions: GateAction[];
  /** Missing depth lines past the ones the chip names. */
  more: number;
}

export interface GateContext {
  /** The account's day P&L the breakers compare; null when unknown. */
  dayPnl?: number | null;
  /** Why the desk's own gate refuses places (padlock PIN, Gateway, spend). */
  blockers?: readonly TradingBlocker[];
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function levelName(level: number): string {
  return BOT_LEVEL_LABELS[(level > 2 ? 2 : level < 0 ? 0 : level) as 0 | 1 | 2] ?? String(level);
}

/** "Depth line 1 / 2 held" with "open IMCC Level 2" and friends, from the backend's facts. */
export function gateLine(g: BotGate, ctx: GateContext = {}): GateLine {
  const d = g.detail ?? {};
  const label = BOT_GATE_LABELS[g.id] ?? g.id;
  const out: GateLine = { id: g.id, ok: Boolean(g.ok), stage: g.stage, text: label, actions: [], more: 0 };
  switch (g.id) {
    case 'level':
      out.text = `${label} ${levelName(Number(d.level ?? 0))}`;
      break;
    case 'allowlist': {
      const n = Number(d.count ?? 0);
      out.text = n > 0 ? `${label} · ${n}` : `${label} empty`;
      if (!out.ok) out.actions.push({ kind: 'add_symbol', label: BOTS_GATE_ADD_SYMBOL });
      break;
    }
    case 'desk_armed': {
      if (out.ok) break;
      const reason = String(d.reason ?? '');
      const blockers = ctx.blockers ?? [];
      if (blockers.includes('disconnected')) {
        out.text = 'IBKR disconnected';
      } else if (blockers.includes('pin') || /disarm/i.test(reason) || !reason) {
        out.text = 'Desk disarmed';
        out.actions.push({ kind: 'unlock', label: BOTS_GATE_UNLOCK });
      } else {
        out.text = prose(reason);
      }
      break;
    }
    case 'depth_lines': {
      const held = list(d.held);
      const missing = list(d.missing);
      const total = held.length + missing.length;
      out.text = total === 0 ? 'Depth lines · no symbols' : `Depth line${total === 1 ? '' : 's'} ${held.length} / ${total} held`;
      for (const sym of missing.slice(0, OPEN_L2_NAMED)) {
        out.actions.push({ kind: 'open_l2', label: BOTS_GATE_OPEN_L2(sym), symbol: sym });
      }
      out.more = Math.max(0, missing.length - OPEN_L2_NAMED);
      break;
    }
    case 'readout': {
      const state = String(d.state ?? '');
      if (out.ok) {
        out.text = `${label} passed`;
      } else if (state === 'failed') {
        out.text = `${label} failed`;
      } else if (state === 'unavailable') {
        out.text = `${label} unavailable — the scoreboard is not open`;
      } else {
        out.text = `${label} ${Number(d.go_triggered ?? 0)} / ${Number(d.min_go ?? 50)}`;
        out.actions.push({ kind: 'readout', label: BOTS_GATE_READOUT_LINK });
      }
      break;
    }
    case 'bot_trip':
      out.text = out.ok
        ? `${label} (${ctx.dayPnl == null ? '—' : fmtUsdCents(ctx.dayPnl)} / ${fmtUsd(BOT_SOFT_BREAKER_USD)})`
        : 'Bot trip fired — Activate re-enables it';
      break;
    case 'day_lock':
      out.text = out.ok ? label : `Day lock until ${String(d.until ?? 'ET midnight')}`;
      break;
    case 'kill_switch':
      out.text = out.ok ? label : 'Kill switch tripped';
      if (!out.ok) out.actions.push({ kind: 'reset_kill', label: BOTS_GATE_RESET_KILL });
      break;
    case 'window': {
      const used = Number(d.entries_today ?? 0);
      const max = Number(d.max_entries ?? 1);
      const shut = d.open === false ? ' · closed now' : '';
      out.text = `${label} ${String(d.start ?? '07:00')}–${String(d.end ?? '10:00')}${shut} · ${used} / ${max} trade today`;
      break;
    }
    default:
      break;
  }
  return out;
}

export function gateLines(gates: BotGate[] | undefined, ctx: GateContext = {}): GateLine[] {
  return (gates ?? []).map(g => gateLine(g, ctx));
}

/** Gates Activate at Strategy needs that are closed. */
export function closedActivateGates(gates: BotGate[] | undefined): BotGate[] {
  return (gates ?? []).filter(g => !g.ok && g.stage === 'activate');
}

export interface HeroSentence {
  lead: string;
  /** "3 of 9 gates", drawn bold; empty when the sentence has no count. */
  count: string;
  tail: string;
}

/**
 * The hero's one-line state under the headline. The level governs a bot on the
 * bot API only: the setup scanner proposes at every level, and nothing in Nova
 * places a proposal on its own yet (#514).
 */
export function heroSentence(session: BotSession): HeroSentence {
  const level = session.level;
  if (level <= 0) {
    return { lead: 'Off: no bot may use the bot API. The setup scanner still watches and proposes; you place.', count: '', tail: '' };
  }
  if (level === 1) return { lead: 'Eyes: a connected bot may watch and propose, never place. You place.', count: '', tail: '' };
  if (!Array.isArray(session.gates)) return { lead: BOTS_HERO_NO_GATES, count: '', tail: '' };
  if (session.live_fire_ready) {
    return {
      lead: `Strategy is live: a connected bot may place your setup under every gate below. ${BOT_STRATEGY_NOT_BUILT}.`,
      count: '',
      tail: '',
    };
  }
  const closed = session.gates.filter(g => !g.ok).length;
  if (closed > 0) {
    return {
      lead: 'Strategy is chosen, but the bot can\'t fire yet: ',
      count: `${closed} of ${session.gates.length} gates`,
      tail: ` ${closed === 1 ? 'is' : 'are'} closed. Until then it proposes like Eyes.`,
    };
  }
  return { lead: `Strategy is chosen and every gate is open. Activate to let a connected bot fire. ${BOT_STRATEGY_NOT_BUILT}.`, count: '', tail: '' };
}

export interface PlayingLine {
  setup: string;
  rest: string;
}

export function playingLine(session: BotSession): PlayingLine {
  const setup = BOT_SETUP_LABELS[session.setup ?? ''] ?? session.setup ?? 'First pullback';
  const n = session.symbol_allowlist?.length ?? 0;
  const shares = session.caps.max_shares;
  return {
    setup,
    rest: ` · ${n} symbol${n === 1 ? '' : 's'} · max ${shares} share${shares === 1 ? '' : 's'} · $${session.caps.bp_budget_usd.toFixed(0)} budget`,
  };
}

/** Whole dollars with a real minus sign: -50 -> "−$50". */
export function fmtUsd(v: number): string {
  return `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString('en-US')}`;
}

/** Dollars and cents with a real minus sign: -9.5 -> "−$9.50"; unknown -> "—". */
export function fmtUsdCents(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const text = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${v < 0 ? '−' : ''}$${text}`;
}

export function fmtR(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const text = Math.abs(v).toFixed(2);
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${text}R`;
}

/** 0-100 progress toward the read-out's go count. */
export function readoutProgress(r: BotReadout | undefined): number {
  if (!r) return 0;
  const min = r.rules?.min_go || 50;
  return Math.max(0, Math.min(100, (100 * (r.go?.triggered ?? 0)) / min));
}

/** Backend prose writes ASCII " -- "; the page sets it as a dash. */
export function prose(text: string | null | undefined): string {
  return (text ?? '').replace(/ -- /g, ' — ');
}

/** Eastern wall-clock time of an epoch second, HH:MM:SS; blank when unknown. */
export function etClock(ts: number | null | undefined): string {
  if (!ts || !Number.isFinite(ts)) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
}
