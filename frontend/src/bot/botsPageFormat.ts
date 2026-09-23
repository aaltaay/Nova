/** Pure helpers for the Bots page (ADR 027): gate lines, the headline, read-out numbers. */
import {
  BOT_GATE_LABELS,
  BOT_LEVEL_LABELS,
  BOT_SETUP_LABELS,
  BOT_SOFT_BREAKER_USD,
} from '../constantGroups/bot';
import type { BotGate, BotReadout, BotSession } from './types';

export interface GateLine {
  id: string;
  ok: boolean;
  stage: string;
  text: string;
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

/** "Depth lines 1 / 2 held -- open IMCC Level 2" and friends, from the backend's facts. */
export function gateLine(g: BotGate): GateLine {
  const d = g.detail ?? {};
  const label = BOT_GATE_LABELS[g.id] ?? g.id;
  let text = label;
  switch (g.id) {
    case 'level': {
      const lvl = Number(d.level ?? 0);
      text = `${label} ${BOT_LEVEL_LABELS[(lvl > 2 ? 2 : lvl) as 0 | 1 | 2] ?? lvl}`;
      break;
    }
    case 'allowlist':
      text = `${label} · ${Number(d.count ?? 0)}${g.ok ? '' : ' -- empty list = the bot does nothing'}`;
      break;
    case 'desk_armed':
      // The backend's reason already names the state ("Desk is disarmed -- ...").
      text = g.ok ? label : String(d.reason ?? 'Desk disarmed -- unlock the padlock');
      break;
    case 'depth_lines': {
      const held = list(d.held);
      const missing = list(d.missing);
      const total = held.length + missing.length;
      text = `Depth line ${held.length} / ${total} held${missing.length ? ` -- open ${missing.join(', ')} Level 2` : ''}`;
      break;
    }
    case 'readout': {
      const n = Number(d.go_triggered ?? 0);
      const min = Number(d.min_go ?? 50);
      text = g.ok ? `${label} passed` : `${label} ${n} / ${min} -- first pullback not proven yet`;
      break;
    }
    case 'bot_trip':
      text = g.ok ? `${label} (${fmtUsd(BOT_SOFT_BREAKER_USD)} trips it)` : 'Bot trip fired -- Activate re-enables it';
      break;
    case 'day_lock':
      text = g.ok ? label : `Day lock until ${String(d.until ?? 'ET midnight')}`;
      break;
    case 'kill_switch':
      text = g.ok ? label : 'Kill switch tripped -- reset it below';
      break;
    case 'window': {
      const start = String(d.start ?? '07:00');
      const end = String(d.end ?? '10:00');
      const used = Number(d.entries_today ?? 0);
      const max = Number(d.max_entries ?? 1);
      text = `${label} ${start}-${end} · ${used} / ${max} trade today`;
      break;
    }
    default:
      break;
  }
  return { id: g.id, ok: Boolean(g.ok), stage: g.stage, text };
}

export function closedActivateGates(gates: BotGate[] | undefined): GateLine[] {
  return (gates ?? []).filter(g => !g.ok && g.stage === 'activate').map(gateLine);
}

/** The hero's one-line state under the headline. */
export function heroSentence(session: BotSession, closed: number): string {
  const level = session.level;
  if (level <= 0) return 'The bot is off: it watches nothing and proposes nothing.';
  if (level === 1) return 'Eyes: the bot watches your setups and proposes. You place.';
  if (session.live_fire_ready) return 'Strategy is live: the bot may place your setup under every gate below.';
  if (closed > 0) {
    return `Strategy is chosen, but the bot can't fire yet: ${closed} gate${closed === 1 ? ' is' : 's are'} closed. Until then it proposes like Eyes.`;
  }
  return 'Strategy is chosen and every gate is open. Activate to let it fire.';
}

export function playingLine(session: BotSession): string {
  const setup = BOT_SETUP_LABELS[session.setup ?? ''] ?? session.setup ?? 'First pullback';
  const n = session.symbol_allowlist?.length ?? 0;
  return `Playing ${setup} · ${n} symbol${n === 1 ? '' : 's'} · max ${session.caps.max_shares} share${session.caps.max_shares === 1 ? '' : 's'} · $${session.caps.bp_budget_usd.toFixed(0)} budget`;
}

/** Whole dollars with a real minus sign: -50 -> "−$50". */
export function fmtUsd(v: number): string {
  return `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString('en-US')}`;
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
