import { describe, expect, it } from 'vitest';
import { activateLock } from './botActivateLock';
import { gateLine } from './botGateWords';
import { botHeaderState } from './botHeaderState';
import { effectiveLevel, ownLevel, strategySetups } from './botLevels';
import { closedProposals, proposalWhy } from './botProposalsModel';
import { botPnlOn } from './useBotPnlToday';
import { dayPnlParts } from './useBotDayPnl';
import { breakerFloor, breakerLimits, breakerPct, markerRange, valueAt } from './breakerScale';
import { deactivatedLine, fmtUsdCents, heroSentence, stocksLine, tradeLine } from './botsPageFormat';
import { etTime, etUntil } from './botWhen';
import { breakers, gates, openGates, session, strategySession } from './botsPageFixtures';
import type { BotAuditEntry } from './types';
import type { HistoryFill } from '../account/accountHistoryTypes';

const gate = (id: string, ok: boolean, detail: Record<string, unknown> = {}, stage = 'activate') => ({ id, ok, stage, detail });
/** 2026-09-30 09:42 ET. */
const AT_0942 = Date.UTC(2026, 8, 30, 13, 42) / 1000;

describe('gate chips (bot/gates.py facts, ADR 042 C)', () => {
  it('names a locked padlock with its link, and any other refusal in its own words', () => {
    const locked = gateLine(gate('padlock', false, { reason: 'Desk is disarmed -- arm trading' }));
    expect(locked.text).toBe('Padlock locked');
    expect(locked.actions).toEqual([{ kind: 'unlock', label: 'unlock padlock' }]);
    expect(locked.why).toBe('The padlock is locked: unlock it first.');
    expect(gateLine(gate('padlock', false, { reason: 'Orders disabled in .env' })).text).toBe('Orders disabled in .env');
    // The legacy id reads the same.
    expect(gateLine(gate('desk_armed', false, { reason: null })).text).toBe('Padlock locked');
    expect(gateLine(gate('padlock', true)).text).toBe('Padlock unlocked');
  });

  it('says the venue in words: Paper trades, Live is not built, a Sim replay is the past', () => {
    expect(gateLine(gate('venue', true, { venue: 'paper' })).text).toBe('Venue Paper');
    const live = gateLine(gate('venue', false, { venue: 'live' }));
    expect(live.text).toBe('Live — the bot does not trade here');
    expect(live.why).toMatch(/Live trading by a bot is not built/);
    expect(gateLine(gate('venue', false, { venue: 'sim', live_edge: false, text: 'Sim off the live edge -- a replay' })).why)
      .toBe('Sim off the live edge — a replay');
  });

  it('is open with one depth line held, and lists the rest as Level 2 links', () => {
    const line = gateLine(gate('depth_lines', true, { held: ['A'], missing: ['B', 'C', 'D'], max_lines: 3 }, 'fire'));
    expect(line.text).toBe('Depth line held · A · IBKR allows 3');
    expect(line.actions.map(a => a.symbol)).toEqual(['B', 'C']);
    expect(line.more).toBe(1);
    const none = gateLine(gate('depth_lines', false, { held: [], missing: ['B'], max_lines: 3 }, 'fire'));
    expect(none.text).toBe('No depth line held · IBKR allows 3');
    expect(none.actions[0]).toMatchObject({ kind: 'open_l2', symbol: 'B' });
    expect(gateLine(gate('depth_lines', false, { held: [], missing: [] }, 'fire')).text).toBe('Depth line · no bot stocks');
  });

  it('reads the level, the setups at Strategy, the stocks and the daily cap', () => {
    expect(gateLine(gate('level', false, { level: 1 })).text).toBe('Master level Eyes — needs Strategy');
    expect(gateLine(gate('level', true, { level: 2 })).text).toBe('Master level Strategy');
    expect(gateLine(gate('setups', true, { at_strategy: ['first_pullback', 'bull_flag'] })).text)
      .toBe('At Strategy · First pullback, Bull flag');
    const none = gateLine(gate('setups', false, { at_strategy: [] }));
    expect(none.text).toBe('No setup at Strategy');
    expect(none.actions[0].kind).toBe('setups');
    expect(gateLine(gate('allowlist', false, { count: 0, auto_entry: 0 }, 'fire'), { venue: 'paper' })).toMatchObject({
      text: 'No stock set to Bot or Auto-entry',
      why: 'No stock is set to Bot or Auto-entry on Paper: set one under Who trades.',
    });
    // Auto-entry stocks count too: Auto-entry buys only while the bot is Active (ADR 042 F).
    expect(gateLine(gate('allowlist', true, { count: 1, auto_entry: 2 }, 'fire')).text).toMatch(/· 1 · Auto-entry 2$/);
    expect(gateLine(gate('daily_cap', true, { count: 0, cap: 1 }, 'fire')).text).toBe('Nova entries 0 / 1 today');
    expect(gateLine(gate('daily_cap', false, { count: 1, cap: 1 }, 'fire')).text).toBe('Daily cap used · 1 / 1 today');
  });

  it('reads the trip, the day lock, the windows, the kill switch and the commissions', () => {
    expect(gateLine(gate('bot_trip', true), { dayPnl: 12.5 }).text).toBe('Bot trip clear ($12.50 / −$50)');
    expect(gateLine(gate('bot_trip', true)).text).toBe('Bot trip clear (— / −$50)');
    expect(gateLine(gate('bot_trip', true), { dayPnl: -12, softUsd: -120 }).text).toBe('Bot trip clear (−$12.00 / −$120)');
    expect(gateLine(gate('bot_trip', false, { fired_at: AT_0942, pnl: -52.1 })).text)
      .toBe('Bot trip fired 09:42 ET (−$52.10) — Activate re-enables it');
    const lock = gateLine(gate('day_lock', false, { until: '2026-10-01T04:00:00-04:00', venue: 'paper' }, 'fire'));
    expect(lock.text).toBe('Day lock on Paper until 04:00 ET on Oct 1');
    const windows = { setups: [{ setup: 'first_pullback', start: '07:00', end: '10:00', open: false, clipped: false },
      { setup: 'red_to_green', start: '09:30', end: '10:00', open: false, clipped: true }] };
    expect(gateLine(gate('window', false, windows, 'fire')).text)
      .toBe('Bot windows closed now · First pullback 07:00–10:00 · Red to green 09:30–10:00 (clipped)');
    const kill = gateLine(gate('kill_switch', false, {}, 'fire'));
    expect(kill.text).toBe('Kill switch tripped');
    expect(kill.actions[0].kind).toBe('reset_kill');
    expect(gateLine(gate('commissions', false, { error: 'database is locked' }, 'fire')).text)
      .toBe('Commissions unreadable — Live entries held until they read');
  });

  it('explains every gate on hover, and a closed one says why now', () => {
    const open = gateLine(gate('level', true, { level: 2 }));
    expect(open.tip).toMatch(/^The master level/);
    expect(open.tip).not.toMatch(/Now:/);
    const closed = gateLine(gate('level', false, { level: 0 }));
    expect(closed.tip).toMatch(/Now: The master level is Off: choose Strategy on the dial first\.$/);
  });
});

describe('Activate (ADR 042 B)', () => {
  it('is locked with every closed Activate gate\'s reason, and never by a fire-stage gate', () => {
    const lock = activateLock(session());
    expect(lock.why).toBe('The master level is Eyes: choose Strategy on the dial first. '
      + 'No setup is at Strategy: set a setup card\'s own switch to Strategy.');
    expect(lock.reenable).toBeNull();
    const fireOnly = activateLock(strategySession({ gates: openGates({ day_lock: { ok: false } }) }));
    expect(fireOnly.why).toBeNull();
  });

  it('says Live is not built and a locked padlock, in the backend\'s words', () => {
    const live = activateLock(strategySession({ gates: openGates({ venue: { ok: false, detail: { venue: 'live' } } }) }));
    expect(live.why).toMatch(/^Nova's bot trades Paper and Sim only\. Live trading by a bot is not built\./);
    const pad = activateLock(strategySession({ gates: openGates({ padlock: { ok: false, detail: { reason: null } } }) }));
    expect(pad.why).toBe('The padlock is locked: unlock it first.');
  });

  it('after a bot trip it may be pressed, and asks in words first', () => {
    const lock = activateLock(strategySession({
      gates: openGates({ bot_trip: { ok: false, detail: { fired_at: AT_0942, pnl: -52.1, until: null } } }),
    }));
    expect(lock.why).toBeNull();
    expect(lock.reenable).toBe('The bot trip fired at 09:42 ET (P&L −$52.10). Activate re-enables the bot for today.');
  });
});

describe('the hero\'s words (ADR 042)', () => {
  it('says what each master level does, on the desk venue, never "live" on Paper', () => {
    expect(heroSentence(session({ level: 0 }))).toMatch(/^Off on Paper: no setup proposes and the bot trades nothing/);
    expect(heroSentence(session({ level: 1 }))).toMatch(/^Eyes on Paper: setups at Eyes or Strategy propose/);
    expect(heroSentence(strategySession())).toBe('Strategy on Paper: the bot may trade GO triggers of First pullback '
      + 'on its 2 stocks set to Bot once you press Activate. Until then they propose like Eyes.');
    const none = strategySession({ setups: [{ id: 'first_pullback', scanner: true, level: 1, effective: 1 }] });
    expect(heroSentence(none)).toMatch(/no setup card is at Strategy/);
    expect(heroSentence(strategySession({ active: true, ready: true }))).toMatch(/^Trading on Paper: the bot buys GO triggers of First pullback/);
    expect(heroSentence(strategySession({ active: true, ready: false, ready_reason: 'every bot window is closed -- 07:00-10:00' })))
      .toBe('Active on Paper: the bot buys GO triggers of First pullback on its 2 stocks set to Bot once nothing below stops it.');
    for (const s of [session({ level: 0 }), session({ level: 1 }), strategySession(), strategySession({ active: true, ready: true })]) {
      expect(heroSentence(s)).not.toMatch(/\blive\b/i);
    }
  });

  it('says the stocks and the sleeve in one line', () => {
    expect(stocksLine(session())).toBe('2 stocks set to Bot · risk $20 a trade · max 1 share · $50 budget · 1 Nova entry a day');
  });

  it('says why the backend turned the bot off', () => {
    expect(deactivatedLine({ at: AT_0942, reason: 'restart', text: null })).toBe('Turned off at 09:42 ET — the backend restarted');
    expect(deactivatedLine({ at: null, reason: 'padlock', text: 'Not active -- you locked the padlock' }))
      .toBe('Turned off — you locked the padlock');
    expect(deactivatedLine(null)).toBe('');
  });

  it('says the bot\'s trade in one line, naming its setup', () => {
    const base = { setup_id: 'S', symbol: 'IMCC', venue: 'paper', venue_day: '2026-09-24', qty: 3, entry_planned: 10.02,
      stop: 9.89, target1: 10.3, risk: 0.14, entry_fill_price: null, exit_price: null, exit_reason: null,
      slippage: null, r: null };
    expect(tradeLine(null)).toBe('');
    expect(tradeLine({ ...base, state: 'entering' })).toBe('Buying IMCC · 3 at 10.02 limit');
    expect(tradeLine({ ...base, setup_type: 'bull_flag', state: 'entering' })).toBe('Buying IMCC (bull flag) · 3 at 10.02 limit');
    expect(tradeLine({ ...base, state: 'open', entry_fill_price: 10.03 }))
      .toBe('In IMCC · 3 @ 10.03 · stop 9.89 · target 10.30');
    expect(tradeLine({ ...base, state: 'exiting', exit_why: 'stop' })).toBe('Closing IMCC · the stop printed');
    expect(tradeLine({ ...base, state: 'closed', exit_reason: 'target', r: 2 })).toBe('Last trade IMCC · target · +2.00R');
    expect(tradeLine({ ...base, state: 'missed', note: 'not filled in 3s -- the price ran past 10.02' }))
      .toBe('Missed IMCC · not filled in 3s — the price ran past 10.02');
  });

  it('formats cents with a real minus sign, and Eastern times', () => {
    expect(fmtUsdCents(-9.5)).toBe('−$9.50');
    expect(fmtUsdCents(null)).toBe('—');
    expect(etTime(AT_0942)).toBe('09:42 ET');
    expect(etTime('2026-09-30T09:42:00-04:00')).toBe('09:42 ET');
    expect(etUntil('2026-09-30')).toBe('00:00 ET on Sep 30');
    expect(etUntil(null)).toBe('');
  });
});

describe('levels (ADR 042 A)', () => {
  it('a setup acts at the lower of its own level and the master', () => {
    const s = session();
    expect(ownLevel(s, 'first_pullback')).toBe(2);
    expect(effectiveLevel(s, 'first_pullback')).toBe(1);
    expect(effectiveLevel(s, 'gap_and_go')).toBeNull();
    // Without the backend's `effective`, min(master, own).
    const raw = session({ level: 2, setups: [{ id: 'bull_flag', scanner: true, level: 2 }] });
    expect(effectiveLevel(raw, 'bull_flag')).toBe(2);
    expect(strategySetups(strategySession())).toEqual(['first_pullback']);
    expect(strategySetups(session())).toEqual([]);
  });
});

describe('header pill, nav dot and rail card (ADR 042)', () => {
  it('says the master level, how many setups are at Strategy, and whether the bot is active -- never a chosen setup', () => {
    const idle = botHeaderState(strategySession());
    expect(idle).toMatchObject({ level: 'L2', name: 'Strategy', detail: '1 at Strategy', state: 'Not active', tone: 'idle' });
    expect(idle.title).toMatch(/at Strategy: First pullback · Not active — press Activate on the Bots page/);
    expect(botHeaderState(strategySession({ active: true, ready: true }))).toMatchObject({ state: 'Active', tone: 'on', reason: null });
    const notReady = botHeaderState(strategySession({ active: true, ready: false, ready_reason: 'no depth line held' }));
    expect(notReady).toMatchObject({ state: 'Active', tone: 'idle', reason: 'Not trading now — no depth line held' });
    expect(botHeaderState(session({ level: 1 }))).toMatchObject({ level: 'L1', name: 'Eyes', state: '' });
    expect(botHeaderState(session({ level: 0 }))).toMatchObject({ level: '', name: 'Off', tone: 'off' });
    const off = botHeaderState(strategySession({ deactivated: { at: null, reason: 'restart', text: null } }));
    expect(off.reason).toBe('Turned off — the backend restarted · press Activate on the Bots page');
    const closed = botHeaderState(session({ level: 2, gates: gates() }));
    expect(closed.title).toMatch(/2 of 13 gates closed: level, setups/);
  });
});

describe('proposals model', () => {
  const row = (partial: Partial<BotAuditEntry>): BotAuditEntry => ({
    timestamp: 1000, level: 2, strategy: null, brain_session_id: null, action: 'setup_proposal',
    inputs: { id: 'p1', symbol: 'IMCC', kind: 'first_pullback', trigger: 1.45, stop: 1.39, closed_at: 1000 },
    reason: 're-armed at new levels', order_id: null, advise_spend: null, outcome: 'rearmed', ...partial,
  });

  it('keeps a withdrawn proposal for half an hour, once, and never one still open', () => {
    expect(closedProposals([row({})], 1000 + 60, new Set())).toHaveLength(1);
    expect(closedProposals([row({})], 1000 + 31 * 60, new Set())).toHaveLength(0);
    expect(closedProposals([row({}), row({ timestamp: 999 })], 1060, new Set())).toHaveLength(1);
    expect(closedProposals([row({})], 1060, new Set(['p1']))).toHaveLength(0);
    expect(closedProposals([row({ outcome: 'proposed' })], 1060, new Set())).toHaveLength(0);
    expect(closedProposals([row({})], 1060, new Set())[0]).toMatchObject({ symbol: 'IMCC', label: 'withdrawn', trigger: 1.45 });
  });

  it('writes the distance, the tape reasons and the target / stop cents', () => {
    const p = { id: 'x', setup_id: 's', symbol: 'GRML', kind: 'first_pullback', trigger: 8.72, entry: 8.73, stop: 8.52,
      target1: 8.92, risk: 0.21, grade: 'A', reasons: ['bid stacking'], created_at: 0, status: 'open' };
    expect(proposalWhy(p, { distance: 0.03 } as never)).toBe('0.03 under the trigger · bid stacking · 20¢ / 20¢');
    expect(proposalWhy(p, { distance: 0 } as never)).toMatch(/^at the trigger/);
    expect(proposalWhy({ ...p, reasons: null }, undefined)).toBe('20¢ / 20¢');
  });
});

describe('the figure the breakers compare (ADR 042 D)', () => {
  it('says how the day P&L was reached, and what is unknown', () => {
    expect(dayPnlParts({ day_pnl: -9.54, meter: { source: 'practice_ledger_day_pnl', commissions: 0 } }))
      .toMatch(/^The practice ledger's day P&L: net liquidation less the 04:00 ET equity/);
    expect(dayPnlParts({ day_pnl: -12.5, meter: { source: 'account_summary', RealizedPnL: -10, UnrealizedPnL: '-1.5', commissions: 1 } }))
      .toBe('realized −$10.00 + unrealized −$1.50 − commissions $1.00');
    expect(dayPnlParts({ day_pnl: null, meter: { commissions_unknown: true, commissions_error: 'OperationalError: locked',
      day_pnl_before_commissions: -60 } }))
      .toBe('Commissions unreadable (OperationalError: locked): before commissions the day is −$60.00 — the breakers still trip on that.');
    expect(dayPnlParts({ day_pnl: null, meter: {} })).toBeNull();
    expect(dayPnlParts(null)).toBeNull();
  });
});

describe('bot P&L and the breaker scale', () => {
  const fill = (partial: Partial<HistoryFill>): HistoryFill => ({
    ts: Date.parse('2026-09-22T14:00:00Z') / 1000, order_id: 1, symbol: 'GRML', side: 'SELL', qty: 1, price: 8.9,
    source: 'bot', bot_id: null, commission: 0.35, fees: 0.01, realized: 0.17, fill_estimated: true, fill_basis: 'quote',
    ...partial,
  });

  it('sums only the bot\'s own fills on the practice day, net of commission', () => {
    const fills = [fill({}), fill({ source: 'manual', realized: 5 }), fill({ ts: Date.parse('2026-09-21T14:00:00Z') / 1000 })];
    expect(botPnlOn(fills, '2026-09-22')).toBeCloseTo(-0.18, 6);
    expect(botPnlOn([fill({ source: null, bot_id: 'b1' })], '2026-09-22')).toBeCloseTo(-0.18, 6);
  });

  it('places a dollar amount on a bar that has room past the all-stop and today\'s loss', () => {
    expect(breakerFloor(-200, null)).toBe(-250);
    expect(breakerFloor(-200, -300)).toBe(-500);
    expect(breakerFloor(-1000, null)).toBe(-2000);
    expect(breakerFloor(-5000, null)).toBe(-7000);
    expect(breakerFloor(-200, -9_000)).toBe(-10_000);
    expect(breakerPct(-250, -250)).toBe(0);
    expect(breakerPct(-50, -250)).toBe(80);
    expect(breakerPct(0, -250)).toBe(100);
    expect(breakerPct(40, -250)).toBe(100);
  });

  it('keeps each marker in its bounds, on $5 steps, and the bot trip above the all-stop (ADR 032)', () => {
    const lim = breakerLimits(breakers({ soft_usd: -50, hard_usd: -200 }));
    expect(markerRange('soft', lim, -200)).toEqual([-195, -5]);
    expect(markerRange('hard', lim, -50)).toEqual([-5000, -55]);
    expect(valueAt(0.5, -250, 5, markerRange('soft', lim, -200))).toBe(-125);
    expect(valueAt(0.513, -250, 5, markerRange('soft', lim, -200))).toBe(-120);
    expect(valueAt(0, -250, 5, markerRange('soft', lim, -200))).toBe(-195);     // never under the all-stop
    expect(valueAt(1, -250, 5, markerRange('hard', lim, -50))).toBe(-55);       // never over the bot trip
    // An API older than ADR 032 keeps the fixed pair and its bounds.
    expect(breakerLimits(undefined)).toMatchObject({ soft: -50, hard: -200, step: 5 });
  });
});
