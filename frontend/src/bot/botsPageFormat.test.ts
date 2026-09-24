import { describe, expect, it } from 'vitest';
import { botHeaderState } from './botHeaderState';
import { closedProposals, proposalWhy } from './botProposalsModel';
import { botPnlOn } from './useBotPnlToday';
import { breakerPosition } from './BotBreakerBar';
import { fmtUsdCents, gateLine, heroSentence } from './botsPageFormat';
import { gates, session } from './botsPageFixtures';
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
    expect(gateLine(gate('bot_trip', true), { dayPnl: 12.5 }).text).toBe('Bot trip clear ($12.50 / −$50)');
    expect(gateLine(gate('bot_trip', true)).text).toBe('Bot trip clear (— / −$50)');
    expect(gateLine(gate('window', false, { start: '07:00', end: '10:00', open: false, entries_today: 0, max_entries: 1 }, 'fire')).text)
      .toBe('Window 07:00–10:00 · closed now · 0 / 1 trade today');
    const kill = gateLine(gate('kill_switch', false, {}, 'fire'));
    expect(kill.text).toBe('Kill switch tripped');
    expect(kill.actions[0].kind).toBe('reset_kill');
    expect(gateLine(gate('allowlist', false, { count: 0 })).actions[0].kind).toBe('add_symbol');
  });

  it('counts every closed gate in the hero, and never claims open gates it was not told about', () => {
    expect(heroSentence(session({ level: 2 })).count).toBe('3 of 9 gates');
    const stale = session({ level: 2 });
    delete stale.gates;
    expect(heroSentence(stale).lead).toMatch(/not reported/);
    expect(heroSentence(session({ level: 2, gates: gates({ level: { ok: true }, depth_lines: { ok: true }, readout: { ok: true } }) })).lead)
      .toMatch(/every gate is open/);
  });

  it('says the level governs a connected bot, never the setup scanner, and that placing a proposal is not built', () => {
    expect(heroSentence(session({ level: 0 })).lead).toMatch(/setup scanner still watches and proposes/);
    expect(heroSentence(session({ level: 0 })).lead).not.toMatch(/watches nothing|proposes nothing/);
    expect(heroSentence(session({ level: 1 })).lead).toMatch(/connected bot may watch and propose, never place/);
    const open = gates({ level: { ok: true }, depth_lines: { ok: true }, readout: { ok: true } });
    expect(heroSentence(session({ level: 2, gates: open })).lead).toMatch(/Automatic placing from a proposal is not built yet/);
    expect(heroSentence(session({ level: 2, gates: open, live_fire_ready: true })).lead)
      .toMatch(/a connected bot may place .* Automatic placing from a proposal is not built yet/);
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
    expect(botHeaderState(session({ level: 0 }), false).title).toMatch(/setup scanner still watches and proposes/);
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

  it('places a P&L between the day lock and zero', () => {
    expect(breakerPosition(-200)).toBe(0);
    expect(breakerPosition(-50)).toBe(75);
    expect(breakerPosition(0)).toBe(100);
    expect(breakerPosition(40)).toBe(100);
  });
});
