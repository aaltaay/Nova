/**
 * The brain in words (ADR 072, mockup brain-switches v1): the pill's states, the panel's rows, and the traders
 * view read at the boundary.
 */
import { describe, expect, it } from 'vitest';
import { readBrainSeat } from './brainSeatApi';
import {
  BRAIN_DONE, BRAIN_HANDED, BRAIN_NOW, BRAIN_OFF, BRAIN_WATCHING, brainStatus, tradersAnswer,
} from './brainSeatFixtures';
import {
  BRAIN_OFF_HELP_GENERIC,
  brainHelp,
  brainLaneRow,
  brainLimitsRow,
  brainNoteHead,
  brainPillText,
  brainPillTitle,
  brainPillWords,
  brainPositionRow,
  brainPositionText,
  brainSubLine,
  brainSwitchTip,
  brainTodayRow,
  fmtMoney,
  fmtWhole,
} from './brainWords';

const pill = (over: Record<string, unknown> = {}) => brainPillWords(brainStatus(over));
const line = (w: { before: string; symbol: string | null; after: string }) => `${w.before}${w.symbol ?? ''}${w.after}`;

describe("the pill's words", () => {
  it('Off: "Brain · Off", muted', () => {
    expect(pill(BRAIN_OFF)).toEqual({ tone: 'off', lead: 'Brain · Off', rest: null, pnl: null });
  });

  it('On, reading: "Brain · Watching SSII", and "Brain · Watching" with no stock', () => {
    const w = pill(BRAIN_WATCHING);
    expect(w).toEqual({ tone: 'on', lead: 'Brain', rest: '· Watching SSII', pnl: null });
    expect(brainPillText(w)).toBe('Brain · Watching SSII');
    const none = pill({ ...BRAIN_WATCHING, symbol: null, lane: { symbol: null, depth: false, tape: false } });
    expect(brainPillText(none)).toBe('Brain · Watching');
  });

  it('On, in a trade: "Brain · In XLAB +$42.00", the figure green; red when it is down', () => {
    const w = pill();
    expect(w).toEqual({ tone: 'on', lead: 'Brain', rest: '· In XLAB', pnl: { text: '+$42.00', tone: 'up' } });
    expect(brainPillText(w)).toBe('Brain · In XLAB +$42.00');
    expect(brainPillTitle(w)).toBe('Brain · In XLAB');
    const down = pill({ position: { symbol: 'XLAB', qty: 200, avg_cost: 4.32, mark: 4.2, unrealized_pnl: -24 } });
    expect(down.pnl).toEqual({ text: '-$24.00', tone: 'dn' });
  });

  it('day stop reached: "Brain · Done for today -$500", red', () => {
    const w = pill(BRAIN_DONE);
    expect(w.tone).toBe('done');
    expect(brainPillText(w)).toBe('Brain · Done for today -$500');
    expect(w.pnl).toEqual({ text: '-$500', tone: 'dn' });
    // Done wins over a switch still On and over a trade it handed you.
    expect(pill({ ...BRAIN_DONE, on: true }).tone).toBe('done');
    expect(brainPillText(pill({ ...BRAIN_DONE, today: { pnl: null } }))).toBe('Brain · Done for today');
  });

  it('Off with a trade handed to you: "Brain · Off · XLAB is yours to close", amber', () => {
    const w = pill(BRAIN_HANDED);
    expect(w).toEqual({ tone: 'wait', lead: 'Brain · Off', rest: '· XLAB is yours to close', pnl: null });
    expect(brainPillText(w)).toBe('Brain · Off · XLAB is yours to close');
  });

  it('On with its program not running: "Brain · On · its program is not running", amber, never a silent block', () => {
    const w = pill({ connected: false });
    expect(w.tone).toBe('wait');
    expect(brainPillText(w)).toBe('Brain · On · its program is not running');
    // Off, a program that is not running is not news: the pill says Off.
    expect(brainPillText(pill({ ...BRAIN_OFF, connected: false }))).toBe('Brain · Off');
    // A backend that does not say (`connected` missing) is not "not running".
    expect(brainPillText(pill({ ...BRAIN_WATCHING, connected: undefined }))).toBe('Brain · Watching SSII');
  });

  it('On with an entry working: "Brain · Buy set SSII"', () => {
    expect(brainPillText(pill({ ...BRAIN_WATCHING, state: 'buy_set' }))).toBe('Brain · Buy set SSII');
  });
});

describe("the panel's rows", () => {
  it('names the venue and the lane: "Paper · lane 3"', () => {
    expect(brainSubLine('paper')).toBe('Paper · lane 3');
    expect(brainSubLine('sim')).toBe('Sim · lane 3');
    expect(brainSubLine(null)).toBe('Lane 3');
  });

  it('heads the note with the ET time: "The brain, 10:41"', () => {
    expect(brainNoteHead(BRAIN_NOW)).toBe('The brain, 10:41');
    expect(brainNoteHead(0)).toBe('The brain');
  });

  it('Lane: both lines up, waiting for Level 2, or no stock yet', () => {
    expect(line(brainLaneRow(brainStatus().lane))).toBe('Level 2 + Time & Sales on XLAB');
    expect(line(brainLaneRow({ symbol: 'XLAB', depth: false, tape: false, why: null }))).toBe("Waiting for XLAB's Level 2");
    expect(line(brainLaneRow({ symbol: null, depth: false, tape: false, why: null }))).toBe('No stock yet');
  });

  it('Position: "200 XLAB at 4.32 · now 4.53", a handed trade as yours to close, or None', () => {
    const text = (s: ReturnType<typeof brainStatus>) => brainPositionText(brainPositionRow(s));
    expect(brainPositionRow(brainStatus())).toEqual({
      short: false, qty: '200', symbol: 'XLAB', at: '4.32', now: '4.53', handed: false, stop: null,
    });
    expect(text(brainStatus())).toBe('200 XLAB at 4.32 · now 4.53');
    expect(text(brainStatus(BRAIN_HANDED))).toBe('200 XLAB · yours to close · stop 4.19');
    expect(brainPositionRow(brainStatus(BRAIN_OFF))).toBeNull();
    expect(text(brainStatus(BRAIN_OFF))).toBe('None');
    const short = brainStatus({ position: { symbol: 'XLAB', qty: -200, avg_cost: 4.32, mark: null, unrealized_pnl: null } });
    expect(text(short)).toBe('Short 200 XLAB at 4.32');
  });

  it('Today: the P&L, a meter that fills as the loss nears the day stop, and the stop', () => {
    expect(brainTodayRow(brainStatus())).toEqual({ pnl: { text: '+$42.00', tone: 'up' }, meter: 0, stop: 'day stop -$500' });
    const down = brainTodayRow(brainStatus({ today: { pnl: -120, loss_limit_usd: -500, tripped_at: null } }));
    expect(down.pnl).toEqual({ text: '-$120.00', tone: 'dn' });
    expect(down.meter).toBeCloseTo(0.24);
    // A day stop written as a positive figure reads the same; a loss past it fills the meter and no more.
    expect(brainTodayRow(brainStatus({ today: { pnl: -900, loss_limit_usd: 500 } })).meter).toBe(1);
    expect(brainTodayRow(brainStatus({ today: { pnl: null, loss_limit_usd: null } })))
      .toEqual({ pnl: null, meter: null, stop: null });
  });

  it('Limits: "1,000 sh · $150 risk · -$500 day", each only when the answer carries it', () => {
    const words = (s: ReturnType<typeof brainStatus>) => brainLimitsRow(s).map(l => `${l.figure} ${l.unit}`).join(' · ');
    expect(words(brainStatus())).toBe('1,000 sh · $150 risk · -$500 day');
    expect(words(brainStatus({ limits: {}, today: { pnl: 0, loss_limit_usd: null } }))).toBe('');
  });

  it('the foot says what Off does while On, naming the stock it holds', () => {
    expect(brainHelp(brainStatus())).toEqual({
      lead: 'Off:',
      text: 'no new trades. Its working entries are cancelled. XLAB and its stop stay as they are, and XLAB is yours to close.',
    });
    expect(brainHelp(brainStatus(BRAIN_WATCHING))).toEqual({ lead: 'Off:', text: BRAIN_OFF_HELP_GENERIC });
    expect(brainHelp(brainStatus(BRAIN_OFF)).lead).toBe('On:');
    expect(brainHelp(brainStatus(BRAIN_DONE))).toEqual({
      lead: null, text: 'The brain reached its day stop today: it stays Off until tomorrow.',
    });
  });

  it('while Nova wakes the brain each trading morning, both helps say Off is for today', () => {
    expect(readBrainSeat(tradersAnswer())?.wakes).toBe(false);          // a backend that does not say
    const on = brainHelp(brainStatus({ ...BRAIN_WATCHING, wakes: true }));
    expect(on).toEqual({ lead: 'Off:', text: `${BRAIN_OFF_HELP_GENERIC} It turns itself On again the next trading morning.` });
    expect(brainHelp(brainStatus({ ...BRAIN_OFF, wakes: true })).text)
      .toBe('the brain may trade again. A trade it handed you stays yours until you close it. It turns itself On again the next trading morning.');
    const refused = { reason: 'TRADER_PAST_FLAT_BY', error: "It is past the brain's flat-by time (15:55 ET): it turns On by itself the next trading morning." };
    expect(brainHelp(brainStatus({ ...BRAIN_OFF, wakes: true, can_turn_on: false, why_not_on: refused })))
      .toEqual({ lead: null, text: refused.error });
  });

  it("the switch's tip is the refusal On would meet, else what the flip does", () => {
    expect(brainSwitchTip(brainStatus(), true)).toBe('Waiting for Nova to answer your last press.');
    expect(brainSwitchTip(brainStatus(), false)).toMatch(/^The brain's switch: On\. Off: no new trades\./);
    expect(brainSwitchTip(brainStatus(BRAIN_DONE), false)).toBe('The brain reached its day stop today: it stays Off until tomorrow.');
    expect(brainSwitchTip(brainStatus(BRAIN_OFF), false)).toMatch(/^The brain's switch: Off\. On: the brain may trade again\./);
  });

  it('formats money with its sign leading the dollar sign', () => {
    expect(fmtMoney(42)).toBe('+$42.00');
    expect(fmtMoney(-1234.5)).toBe('-$1,234.50');
    expect(fmtMoney(0)).toBe('$0.00');
    expect(fmtWhole(-500)).toBe('-$500');
    expect(fmtWhole(150)).toBe('$150');
    expect(fmtWhole(-0.2)).toBe('$0');
  });
});

describe('the traders view at the boundary', () => {
  it("reads the brain's TRADER, upper-casing its stocks", () => {
    const s = readBrainSeat(tradersAnswer({
      symbol: 'xlab', lane: { symbol: 'xlab', depth: true, tape: true, why: 'held the bid' },
      reading: [{ symbol: 'ssii', text: 'flat top', source: 'level1' }, { symbol: 'xlab', text: 'go', source: 'lane' },
        { text: 'no stock' }, 'junk'],
    }))!;
    expect(s.venue).toBe('paper');
    expect(s.symbol).toBe('XLAB');
    expect(s.lane).toEqual({ symbol: 'XLAB', depth: true, tape: true, why: 'held the bid' });
    expect(s.reading).toEqual([
      { symbol: 'SSII', text: 'flat top', source: 'level1' }, { symbol: 'XLAB', text: 'go', source: 'lane' },
    ]);
    expect(s.position).toEqual({ symbol: 'XLAB', qty: 200, avg_cost: 4.32, mark: 4.53, unrealized_pnl: 42 });
    expect(s.limits).toMatchObject({ max_shares: 1000, risk_usd: 150, budget_usd: 25_000, flat_by: '15:55' });
    expect(s.connected).toBe(true);
    expect(s.events).toEqual([{ at: BRAIN_NOW, kind: 'fill', symbol: 'XLAB', text: 'bought 200 XLAB at 4.32' }]);
    expect(s.read_error).toBeNull();
  });

  it('a backend from before the brain\'s door reads with nothing invented', () => {
    const old = readBrainSeat({
      schema_version: 1, generated_at: 9, venue: 'paper', error: 'trader-switches.json could not be read',
      traders: { brain: { name: 'brain', on: true, state: 'watching', text: 'Brain · Watching',
        lane: { symbol: null, depth: false, tape: false }, position: null, handed: [], today: { pnl: null },
        limits: { max_shares: 1000 }, note: null } },
    })!;
    expect(old.connected).toBeNull();
    expect(old.reading).toEqual([]);
    expect(old.events).toEqual([]);
    expect(old.lane.why).toBeNull();
    expect(old.read_error).toBe('trader-switches.json could not be read');
    expect(brainPillText(brainPillWords(old))).toBe('Brain · Watching');
  });

  it('an answer without a brain is not the view; an unknown state reads from the switch', () => {
    expect(readBrainSeat({ schema_version: 1, traders: { claude: {} } })).toBeNull();
    expect(readBrainSeat(null)).toBeNull();
    expect(readBrainSeat('traders')).toBeNull();
    expect(readBrainSeat(tradersAnswer({ state: 'dreaming', on: false }))!.state).toBe('off');
    expect(readBrainSeat(tradersAnswer({ state: 'dreaming', on: true }))!.state).toBe('watching');
  });
});
