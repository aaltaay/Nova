import { describe, expect, it } from 'vitest';
import { botHeaderState } from './botHeaderState';
import { closedProposals, proposalWhy } from './botProposalsModel';
import { botPnlOn } from './useBotPnlToday';
import { breakerFloor, breakerLimits, breakerPct, markerRange, valueAt } from './breakerScale';
import { fmtUsdCents, gateLine, heroSentence, tradeLine } from './botsPageFormat';
import { breakers, gates, session } from './botsPageFixtures';
import type { BotAuditEntry } from './types';
import type { HistoryFill } from '../account/accountHistoryTypes';

const gate = (id: string, ok: boolean, detail: Record<string, unknown> = {}, stage = 'activate') => ({ id, ok, stage, detail });

describe('gate chips (bot/gates.py facts, approved mockup v4)', () => {
  it('names a disarmed desk with the padlock link, a lost Gateway without one', () => {
    const disarmed = gateLine(gate('desk_armed', false, { reason: 'Desk is disarmed -- arm trading' }));
    expect(disarmed.text).toBe('Desk disarmed');
    expect(disarmed.actions).toEqual([{ kind: 'unlock', label: 'unlock padlock' }]);
    const offline = gateLine(gate('desk_armed', false, { reason: 'x' }), { blockers: ['disconnected'] });
    expect(offline.text).toBe('IBKR disconnected');
    expect(offline.actions).toEqual([]);
    const spend = gateLine(gate('desk_armed', false, { reason: 'Orders disabled in .env' }));
    expect(spend.text).toBe('Orders disabled in .env');
  });

  it('links each missing depth line up to two, then counts the rest', () => {
    const line = gateLine(gate('depth_lines', false, { held: ['A'], missing: ['B', 'C', 'D'] }, 'fire'));
    expect(line.text).toBe('Depth lines 1 / 4 held');
    expect(line.actions.map(a => a.symbol)).toEqual(['B', 'C']);
    expect(line.more).toBe(1);
    expect(gateLine(gate('depth_lines', false, { held: [], missing: [] }, 'fire')).text).toBe('Depth lines · no symbols');
  });

  it('reads the read-out, the trip, the window and the kill switch', () => {
    expect(gateLine(gate('readout', false, { state: 'failed' })).text).toBe('Read-out failed');
    expect(gateLine(gate('readout', true, {})).text).toBe('Read-out passed');
    // ADR 030: Paper and Sim do not wait on it; the count still says how far Live is.
    const waived = gateLine(gate('readout', true, { waived: true, venue: 'paper', go_triggered: 0, min_go: 50 }));
    expect(waived.text).toBe('Read-out not needed on Paper · 0 / 50');
    expect(waived.actions).toEqual([]);
    expect(gateLine(gate('bot_trip', true), { dayPnl: 12.5 }).text).toBe('Bot trip clear ($12.50 / −$50)');
    expect(gateLine(gate('bot_trip', true)).text).toBe('Bot trip clear (— / −$50)');
    // ADR 032: the chip reads the desk venue's own bot trip.
    expect(gateLine(gate('bot_trip', true), { dayPnl: -12, softUsd: -120 }).text).toBe('Bot trip clear (−$12.00 / −$120)');
    // ADR 031: the read-out link names the chosen setup.
    expect(gateLine(gate('readout', false, { state: 'collecting' }), { setup: 'bull_flag' }).actions[0].label)
      .toBe('bull flag not proven yet');
    expect(gateLine(gate('window', false, { start: '07:00', end: '10:00', open: false, entries_today: 0, max_entries: 1 }, 'fire')).text)
      .toBe('Window 07:00–10:00 · closed now · 0 / 1 trade today');
    const kill = gateLine(gate('kill_switch', false, {}, 'fire'));
    expect(kill.text).toBe('Kill switch tripped');
    expect(kill.actions[0].kind).toBe('reset_kill');
    expect(gateLine(gate('allowlist', false, { count: 0 })).actions[0].kind).toBe('add_symbol');
    // #564: a Live commission read that fails holds new entries, and the chip says so.
    expect(gateLine(gate('commissions', true, {}, 'fire')).text).toBe('Commissions read');
    expect(gateLine(gate('commissions', false, { error: 'OperationalError: database is locked' }, 'fire')).text)
      .toBe('Commissions unreadable — Live entries held until they read');
  });

  it('counts every closed gate in the hero, and never claims open gates it was not told about', () => {
    expect(heroSentence(session({ level: 2 })).count).toBe('3 of 9 gates');
    const stale = session({ level: 2 });
    delete stale.gates;
    expect(heroSentence(stale).lead).toMatch(/not reported/);
    expect(heroSentence(session({ level: 2, gates: gates({ level: { ok: true }, depth_lines: { ok: true }, readout: { ok: true } }) })).lead)
      .toMatch(/every gate is open/);
  });

  it('says Off scores the chosen setup in silence and Eyes proposes, and that at Strategy Nova\'s own bot trades on Paper and Sim', () => {
    // ADR 031 decision A: Off watches and scores, silently -- no proposals.
    expect(heroSentence(session({ level: 0 })).lead).toMatch(/first pullback scanner watches and scores in silence — no proposals/);
    expect(heroSentence(session({ level: 0, setup: 'bull_flag' })).lead).toMatch(/bull flag scanner/);
    expect(heroSentence(session({ level: 1 })).lead).toMatch(/proposes when a setup is near its trigger and the tape says go/);
    expect(heroSentence(session({ level: 1 })).lead).toMatch(/Nothing places; you do/);
    const open = gates({ level: { ok: true }, depth_lines: { ok: true }, readout: { ok: true } });
    expect(heroSentence(session({ level: 2, gates: open })).lead).toMatch(/Nova's own bot trades Paper and Sim only/);
    const paper = gates({ level: { ok: true }, depth_lines: { ok: true },
      readout: { ok: true, detail: { waived: true, venue: 'paper', go_triggered: 0, min_go: 50 } } });
    expect(heroSentence(session({ level: 2, gates: paper, readout_required: false })).lead)
      .toBe('Strategy is chosen and every gate is open. Activate and the bot trades the first pullback on Paper.');
    const runner = { brain_id: 'nova-first-pullback', playing: true, reason: null };
    expect(heroSentence(session({ level: 2, gates: paper, live_fire_ready: true, runner })).lead)
      .toMatch(/^Strategy is live on Paper: the bot buys the first pullback itself/);
    const offLive = { ...runner, playing: false, reason: 'Nova\'s bot trades Paper and Sim only' };
    expect(heroSentence(session({ level: 2, gates: open, live_fire_ready: true, runner: offLive })).lead)
      .toMatch(/a connected bot may place .* Nova's own bot does not play here — Nova's bot trades Paper and Sim only/);
  });

  it('says the bot\'s trade in one line', () => {
    const base = { setup_id: 'S', symbol: 'IMCC', venue: 'paper', venue_day: '2026-09-24', qty: 3, entry_planned: 10.02,
      stop: 9.89, target1: 10.3, risk: 0.14, entry_fill_price: null, exit_price: null, exit_reason: null,
      slippage: null, r: null };
    expect(tradeLine(null)).toBe('');
    expect(tradeLine({ ...base, state: 'entering' })).toBe('Buying IMCC · 3 at 10.02 limit');
    expect(tradeLine({ ...base, state: 'open', entry_fill_price: 10.03 }))
      .toBe('In IMCC · 3 @ 10.03 · stop 9.89 · target 10.30');
    expect(tradeLine({ ...base, state: 'exiting', exit_why: 'stop' })).toBe('Closing IMCC · the stop printed');
    expect(tradeLine({ ...base, state: 'closed', exit_reason: 'target', r: 2 })).toBe('Last trade IMCC · target · +2.00R');
    expect(tradeLine({ ...base, state: 'missed', note: 'not filled in 3s -- the price ran past 10.02' }))
      .toBe('Missed IMCC · not filled in 3s — the price ran past 10.02');
  });

  it('formats cents with a real minus sign', () => {
    expect(fmtUsdCents(-9.5)).toBe('−$9.50');
    expect(fmtUsdCents(null)).toBe('—');
  });
});

describe('header pill and nav dot', () => {
  it('says the level, the setup and whether the bot is in control', () => {
    expect(botHeaderState(session({ level: 2 }), false)).toMatchObject({ level: 'L2', name: 'First pullback', state: 'Not active', tone: 'idle' });
    expect(botHeaderState(session({ level: 2 }), true)).toMatchObject({ state: 'Active', tone: 'on' });
    expect(botHeaderState(session({ level: 1 }), false)).toMatchObject({ level: 'L1', state: 'Eyes' });
    expect(botHeaderState(session({ level: 0 }), false)).toMatchObject({ level: '', name: 'Off', tone: 'off' });
    expect(botHeaderState(session({ level: 2 }), false).title).toMatch(/3 of 9 gates closed: level, depth lines, readout/);
    expect(botHeaderState(session({ level: 0 }), false).title).toMatch(/chosen setup scores in silence -- no proposals/);
    expect(botHeaderState(session({ level: 2, setup: 'red_to_green' }), false).name).toBe('Red to green');
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
