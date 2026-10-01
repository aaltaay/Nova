/**
 * Every gate between the bot and a trade (backend bot/gates.py, ADR 042 C) in words,
 * pure: the chip's text, its hover, the one action that opens it, and -- for a closed
 * gate -- the sentence that says why, which Activate's `data-why` and the hero's
 * headline reuse. Nothing here decides whether a gate is open: the backend does.
 * `activate`-stage gates are what Activate needs; `fire`-stage gates are what each
 * order still meets.
 */
import { BOT_GATE_COMMISSIONS_HELD, BOT_GATE_LABELS, BOT_GATE_TIPS, BOT_SOFT_BREAKER_USD } from '../constantGroups/bot';
import {
  BOTS_GATE_ADD_SYMBOL,
  BOTS_GATE_OPEN_L2,
  BOTS_GATE_RESET_KILL,
  BOTS_GATE_SETUPS,
  BOTS_GATE_UNLOCK,
  BOTS_VENUE_NAMES,
} from '../constantGroups/bots_page';
import { levelName, setupLabelOf, setupNames } from './botLevels';
import { etTime, etUntil, usdCents } from './botWhen';
import type { BotGate, BotSession } from './types';

/** How many missing depth lines a chip names before "+N more". */
const OPEN_L2_NAMED = 2;
/** The legacy id of the padlock gate (before ADR 042). */
const PADLOCK_IDS = new Set(['padlock', 'desk_armed']);

export type GateActionKind = 'unlock' | 'open_l2' | 'add_symbol' | 'setups' | 'reset_kill';

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
  /** What the gate checks, and -- closed -- why it is closed now. */
  tip: string;
  /** Why it is closed, as a sentence; null while it is open. */
  why: string | null;
  actions: GateAction[];
  /** Missing depth lines past the ones the chip names. */
  more: number;
}

export interface GateContext {
  /** The venue's day P&L the breakers compare; null when unknown. */
  dayPnl?: number | null;
  /** Why the desk's own gate refuses places: `pin` (the padlock), `disconnected`, `spend`. */
  blockers?: readonly string[];
  /** The desk venue's bot trip (ADR 032); the default when the API keeps none. */
  softUsd?: number;
  /** The desk venue ("live" | "paper" | "sim"), for the words. */
  venue?: string | null;
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim().replace(/ -- /g, ' — ') : null;
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function venueName(v: unknown): string {
  return BOTS_VENUE_NAMES[String(v ?? '')] ?? 'this venue';
}

/** Whole dollars with a real minus: -50 -> "−$50". */
function wholeUsd(v: number): string {
  return `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString('en-US')}`;
}

/** The gate context the hero draws with: the day P&L, the desk's blockers, the venue's bot trip. */
export function gateContext(session: BotSession, dayPnl: number | null, blockers?: readonly string[]): GateContext {
  return { dayPnl, blockers, softUsd: session.breakers?.soft_usd, venue: session.breakers?.venue ?? session.level_venue ?? null };
}

type Words = Pick<GateLine, 'text' | 'why'> & { actions?: GateAction[]; more?: number };

function venueWords(ok: boolean, d: Record<string, unknown>): Words {
  const v = String(d.venue ?? '');
  const own = text(d.text);
  if (ok) return { text: `Venue ${venueName(v)}${v === 'sim' ? ' · live edge' : ''}`, why: null };
  if (v === 'live') {
    return { text: 'Live — the bot does not trade here',
      why: own ?? 'Nova\'s bot trades Paper and Sim only. Live trading by a bot is not built.' };
  }
  if (v === 'sim') {
    return { text: 'Sim replay — the bot trades Sim at the live edge only',
      why: own ?? 'This Sim desk is a replay, the past: the bot trades Sim only at the live edge (Follow wall clock).' };
  }
  return { text: 'Venue unreadable', why: own ?? 'The desk venue cannot be read, so the bot stays off.' };
}

function padlockWords(ok: boolean, d: Record<string, unknown>, ctx: GateContext): Words {
  if (ok) return { text: 'Padlock unlocked', why: null };
  const reason = text(d.reason) ?? '';
  if (!reason || /disarm|padlock|lock|arm /i.test(reason) || (ctx.blockers ?? []).includes('pin')) {
    return { text: 'Padlock locked', why: 'The padlock is locked: unlock it first.',
      actions: [{ kind: 'unlock', label: BOTS_GATE_UNLOCK }] };
  }
  return { text: reason, why: reason };
}

function depthWords(ok: boolean, d: Record<string, unknown>): Words {
  const held = list(d.held);
  const missing = list(d.missing);
  const max = num(d.max_lines);
  const actions: GateAction[] = missing.slice(0, OPEN_L2_NAMED)
    .map(sym => ({ kind: 'open_l2', label: BOTS_GATE_OPEN_L2(sym), symbol: sym }));
  const more = Math.max(0, missing.length - OPEN_L2_NAMED);
  if (held.length + missing.length === 0) {
    return { text: 'Depth line · no bot stocks', why: 'No stock is set to Bot, so no depth line can be held for one.' };
  }
  const cap = max != null ? ` · IBKR allows ${max}` : '';
  if (ok || held.length > 0) {
    return { text: `Depth line held · ${held.join(', ')}${cap}`, why: null, actions, more };
  }
  return { text: `No depth line held${cap}`, actions, more,
    why: 'Nova holds no Level 2 line on any bot stock, so the bot cannot read a tape at a trigger: open one\'s Level 2.' };
}

function windowWords(ok: boolean, d: Record<string, unknown>): Words {
  const rows = Array.isArray(d.setups) ? d.setups.filter((r): r is Record<string, unknown> => r != null && typeof r === 'object') : null;
  if (rows == null) {
    // An API before ADR 042: one window for the chosen setup.
    const shut = d.open === false ? ' · closed now' : '';
    return { text: `Bot window ${String(d.start ?? '—')}–${String(d.end ?? '—')}${shut}`, why: ok ? null : 'The bot window is closed now.' };
  }
  if (rows.length === 0) return { text: 'Bot window — no setup at Strategy', why: 'No setup at Strategy has a bot window.' };
  const one = (r: Record<string, unknown>) =>
    `${setupLabelOf(String(r.setup ?? ''))} ${String(r.start ?? '—')}–${String(r.end ?? '—')}${r.clipped ? ' (clipped)' : ''}`;
  const open = rows.filter(r => r.open === true);
  if (ok || open.length) return { text: `Bot window open · ${open.map(one).join(' · ')}`, why: null };
  return { text: `Bot windows closed now · ${rows.map(one).join(' · ')}`,
    why: `Every setup at Strategy is outside its bot window now: ${rows.map(one).join(', ')}.` };
}

function capWords(ok: boolean, d: Record<string, unknown>): Words {
  const count = num(d.count) ?? 0;
  const cap = num(d.cap);
  const of = cap == null ? `${count}` : `${count} / ${cap}`;
  if (ok) return { text: `Nova entries ${of} today`, why: null };
  return { text: `Daily cap used · ${of} today`,
    why: `Nova's automatic entries on this venue today reached the cap (${of}); a missed entry gives the day back.` };
}

function wordsFor(g: BotGate, ctx: GateContext): Words {
  const d = g.detail ?? {};
  const ok = Boolean(g.ok);
  const label = BOT_GATE_LABELS[g.id] ?? g.id.replace(/_/g, ' ');
  switch (g.id) {
    case 'venue':
      return venueWords(ok, d);
    case 'level': {
      const name = levelName(d.level ?? 0);
      return ok ? { text: `${label} Strategy`, why: null }
        : { text: `${label} ${name} — needs Strategy`, why: `The master level is ${name}: choose Strategy on the dial first.` };
    }
    case 'setups': {
      const ids = list(d.at_strategy);
      return ok ? { text: `At Strategy · ${setupNames(ids)}`, why: null }
        : { text: 'No setup at Strategy', why: 'No setup is at Strategy: set a setup card\'s own switch to Strategy.',
          actions: [{ kind: 'setups', label: BOTS_GATE_SETUPS }] };
    }
    case 'padlock':
    case 'desk_armed':
      return padlockWords(ok, d, ctx);
    case 'allowlist': {
      const n = num(d.count) ?? 0;
      return ok ? { text: `${label} · ${n}`, why: null }
        : { text: 'No stock set to Bot', why: `No stock is set to Bot on ${venueName(ctx.venue)}: add one under Who trades.`,
          actions: [{ kind: 'add_symbol', label: BOTS_GATE_ADD_SYMBOL }] };
    }
    case 'depth_lines':
      return depthWords(ok, d);
    case 'bot_trip': {
      if (ok) {
        const pnl = ctx.dayPnl == null ? '—' : usdCents(ctx.dayPnl);
        return { text: `Bot trip clear (${pnl} / ${wholeUsd(ctx.softUsd ?? BOT_SOFT_BREAKER_USD)})`, why: null };
      }
      const when = etTime(d.fired_at as string | number | null);
      const pnl = usdCents(num(d.pnl));
      return { text: `Bot trip fired${when ? ` ${when}` : ''}${pnl ? ` (${pnl})` : ''} — Activate re-enables it`,
        why: `The bot trip fired${when ? ` at ${when}` : ''}${pnl ? ` (P&L ${pnl})` : ''}.` };
    }
    case 'day_lock': {
      if (ok) return { text: 'No day lock', why: null };
      const until = etUntil(d.until as string | number | null);
      const venue = venueName(d.venue ?? ctx.venue);
      return { text: `Day lock on ${venue}${until ? ` until ${until}` : ''}`,
        why: `The all-stop locked buys on ${venue}${until ? ` until ${until}` : ' until 04:00 ET'}.` };
    }
    case 'kill_switch':
      return ok ? { text: 'Kill switch off', why: null }
        : { text: 'Kill switch tripped', why: 'The kill switch is tripped: new buys are refused on every venue until you reset it.',
          actions: [{ kind: 'reset_kill', label: BOTS_GATE_RESET_KILL }] };
    case 'window':
      return windowWords(ok, d);
    case 'daily_cap':
      return capWords(ok, d);
    case 'extended_hours': {
      const own = text(d.text);
      return ok ? { text: own ?? 'Hours · buys allowed now', why: null }
        : { text: own ?? 'Outside 09:30–16:00 ET · extended hours off',
          why: 'Outside 09:30–16:00 ET and the sleeve does not allow extended hours: the bot and Auto-entry skip triggers now.' };
    }
    case 'commissions':
      return ok ? { text: 'Commissions read', why: null }
        : { text: BOT_GATE_COMMISSIONS_HELD, why: 'Live\'s commissions cannot be read, so new entries wait.' };
    default:
      return { text: ok ? label : `${label} closed`, why: ok ? null : text(d.reason) ?? `${label} is closed.` };
  }
}

/** One gate as a chip: its words, its hover, and the action that opens it. */
export function gateLine(g: BotGate, ctx: GateContext = {}): GateLine {
  const w = wordsFor(g, ctx);
  const ok = Boolean(g.ok);
  const id = PADLOCK_IDS.has(g.id) ? 'padlock' : g.id;
  const base = BOT_GATE_TIPS[id] ?? '';
  const tip = ok || !w.why ? base : `${base}\nNow: ${w.why}`;
  return { id: g.id, ok, stage: g.stage, text: w.text, tip, why: ok ? null : w.why, actions: w.actions ?? [], more: w.more ?? 0 };
}

export function gateLines(gates: BotGate[] | undefined, ctx: GateContext = {}): GateLine[] {
  return (gates ?? []).map(g => gateLine(g, ctx));
}

/** The closed gates of one stage. */
export function closedGates(gates: BotGate[] | undefined, stage: 'activate' | 'fire'): BotGate[] {
  return (gates ?? []).filter(g => !g.ok && (stage === 'activate' ? g.stage === 'activate' : g.stage !== 'activate'));
}
