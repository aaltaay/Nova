import { describe, expect, it } from 'vitest';
import { flowLine } from './flowWords';
import {
  funnelSteps,
  gradeWords,
  otherSetups,
  rowsBySymbol,
  setupTypeOf,
  signedPct,
  stateWords,
  tapeWords,
  toGoWords,
  triggerWords,
  windowWords,
} from './setupWords';
import type { SetupRow } from './types';

function row(partial: Partial<SetupRow> = {}): SetupRow {
  return {
    symbol: 'ABCD', setup_type: 'first_pullback', state: 'armed', reason: 'trigger 4.86, stop 4.62, risk 0.25',
    kind: 'first_pullback', nth: 0, setup_id: 's1',
    setup: { trigger: 4.86, entry: 4.87, stop: 4.62, risk: 0.25, target1: 5.37, pullback_bars: 2, leg_high: 4.9,
      leg_low: 4.4, leg_pct: 0.11 },
    leg: { t: 0, high: 4.9, low: 4.4, pct: 0.11 }, last_price: 4.82, distance: 0.04, grade: 'A', pillars: null,
    tape: null, proposal: null, outcome: null, bar_r: null, mfe: null, mae: null,
    ...partial,
  };
}

describe('every setup in its own words (ADR 031)', () => {
  it('reads an older API\'s row as the first pullback\'s', () => {
    expect(setupTypeOf({})).toBe('first_pullback');
    expect(setupTypeOf({ setup_type: 'bull_flag' })).toBe('bull_flag');
  });

  it('says each state in the setup\'s terms', () => {
    expect(stateWords(row({ state: 'leg', setup: null })).text).toBe('Leg up +11%');
    expect(stateWords(row({ setup_type: 'bull_flag', state: 'leg', setup: null,
      leg: { t: 0, high: 4.35, low: 4.1, pct: 0.061, bars: 3 } })).text).toBe('Pole · 3 green');
    expect(stateWords(row({ setup_type: 'bull_flag', setup: { ...row().setup!, detail: { flag_bars: 2 } } })).text)
      .toBe('Flag · 2 bars');
    expect(stateWords(row({ setup_type: 'flat_top_breakout', state: 'leg', setup: null })).text).toBe('Pushing HOD');
    expect(stateWords(row({ setup_type: 'flat_top_breakout', setup: { ...row().setup!, pullback_bars: 4 } })).text)
      .toBe('Base · 4 bars');
    expect(stateWords(row({ setup_type: 'red_to_green', leg: { t: 0, high: 2.51, low: 2.38, pct: -0.041, bars: 3 } })).text)
      .toBe('Red −4.1%');
    expect(stateWords(row({ setup_type: 'red_to_green', state: 'near' })).text).toBe('Near the open');
    expect(stateWords(row({ state: 'pullback', setup: null })).text).toBe('Pullback · held back');
  });

  it('stamps a trigger and a failure with their Eastern time', () => {
    const at = Date.parse('2026-09-24T13:33:00Z') / 1000;     // 09:33 ET
    expect(stateWords(row({ state: 'triggered', setup: { ...row().setup!, triggered_at: at } })).text).toBe('Triggered 09:33');
    expect(stateWords(row({ setup_type: 'red_to_green', state: 'triggered',
      setup: { ...row().setup!, triggered_at: at } })).text).toBe('Reclaimed 09:33');
    expect(stateWords(row({ state: 'failed', failed_at: at + 300 })).text).toBe('Failed 09:38');
  });

  it('says a flat top that broke is waiting for a candle to hold', () => {
    const broke = Date.parse('2026-09-24T13:41:00Z') / 1000;
    const w = stateWords(row({ setup_type: 'flat_top_breakout', state: 'near',
      setup: { ...row().setup!, detail: { entry_mode: 'hold', broke_at: broke, hold_bars: 3 } } }));
    expect(w.text).toBe('Broke · wants a hold');
    expect(w.tip).toMatch(/Broke the 4\.86 high at 09:41 ET\. Now the first of the next 3 candles/);
    // Until a candle holds, the entry and stop are the hold candle's, not the break's.
    expect(w.tip).toMatch(/entry the hold candle's close \+1c · stop the hold candle's low/);
    expect(triggerWords(row({ setup_type: 'flat_top_breakout', state: 'armed',
      setup: { ...row().setup!, detail: { entry_mode: 'hold' } } })).tip).toMatch(/Hold entry/);
  });

  it('puts what the state means, the numbers and the scanner\'s own words in the hover', () => {
    const w = stateWords(row({ reason: 'trigger 4.86 -- read the tape' }));
    expect(w.title).toBe('Armed · First pullback');
    expect(w.tip.split('\n')).toEqual([
      'The pullback is in place. The trigger is the last pullback candle\'s high; the stop is the pullback low. Waiting for price to come back up.',
      'Leg +11% to a new high 4.90 (from 4.40).',
      'Trigger 4.86 · entry 4.87 · stop 4.62 · risk 25¢ a share · target 1 5.37.',
      'Now: trigger 4.86 — read the tape',
    ]);
    expect(triggerWords(row()).tip).toMatch(/^Trigger 4\.86: the last pullback candle's high\./);
    expect(triggerWords(row({ setup_type: 'red_to_green' })).tip).toMatch(/^Trigger 4\.86: the open\./);
  });

  it('says how far to go in cents, and how a triggered setup went', () => {
    expect(toGoWords(row()).text).toBe('4¢');
    expect(toGoWords(row({ distance: 0 })).text).toBe('at');
    expect(toGoWords(row({ distance: 1.25 })).text).toBe('$1.25');
    expect(toGoWords(row({ state: 'leg', distance: null })).text).toBe('·');
    const done = toGoWords(row({ state: 'triggered', distance: null, outcome: 'target_first', bar_r: 0.9 }));
    expect(done.text).toBe('+0.90R');
    expect(done.tip).toMatch(/target 1 first \(\+0\.90R\)/);
  });

  it('reads the tape with its reasons and numbers', () => {
    expect(tapeWords(row({ state: 'leg' }))).toBeNull();
    expect(tapeWords(row())?.text).toBe('·');
    const tape = tapeWords(row({ tape: { verdict: 'wait', reasons: ['25k-share seller at 4.87 is not thinning'],
      metrics: { best_bid: 4.85, best_ask: 4.87, spread: 0.02, ask_prints: 1, bid_prints: 4, ask_volume: 200,
        bid_volume: 5400, wall_size: 25000, wall_price: 4.87, window_sec: 10 } } }));
    expect(tape?.text).toBe('WAIT');
    expect(tape?.tip.split('\n')).toEqual([
      expect.stringMatching(/^WAIT: not yet/),
      'Why: 25k-share seller at 4.87 is not thinning.',
      'bid 4.85 × ask 4.87 · spread 2¢ · 1 prints at the ask (200) vs 4 at the bid (5.4k) · biggest seller at the level 25k at 4.87 (last 10 s).',
    ]);
  });

  it('grades with every pillar and its value, an unknown never read as failed', () => {
    const w = gradeWords(row({ grade: 'B', pillars: { price: 4.82, change_pct: 42, rvol: 6.1, float: null, news: true,
      headline: 'FDA clearance', catalyst: null, checks: { price: true, change: true, rvol: true, float: null, news: true } } as never }));
    expect(w.text).toBe('B');
    expect(w.tip).toMatch(/✓ Price: 4\.82/);
    expect(w.tip).toMatch(/✓ Up on the day: \+42%/);
    expect(w.tip).toMatch(/\? Float: unknown/);
    expect(w.tip).toMatch(/✓ News \(a real catalyst\): FDA clearance/);
    expect(gradeWords(row({ grade: null })).text).toBe('·');
  });

  it('counts today\'s funnel in each setup\'s words', () => {
    const counts = { watching: 14, forming: 5, armed: 3, near: 1, triggered: 1, failed: 1, filtered: 0, proposed: 1 };
    expect(funnelSteps('bull_flag', counts).map(s => `${s.n} ${s.word}`))
      .toEqual(['5 poles', '3 flags', '1 near', '1 broke out', '1 failed', '1 proposed']);
    expect(funnelSteps('red_to_green', { ...counts, filtered: 2 }).map(s => s.word))
      .toEqual(['red', 'armed', 'near', 'reclaimed', 'failed', 'proposed', 'filtered']);
    expect(funnelSteps('first_pullback', null)).toEqual([]);
  });

  it('says the window as the card does', () => {
    const summary = (state: string) => ({ window: { start: '09:30', end: '10:30', state } }) as never;
    expect(windowWords(summary('before'))).toBe('opens 09:30');
    expect(windowWords(summary('open'))).toBe('window 09:30–10:30');
    expect(windowWords(summary('after'))).toBe('window closed 10:30');
    expect(windowWords(null)).toBe('');
  });

  it('keeps a symbol\'s setups together, most advanced first, and names the others', () => {
    const fp = row({ symbol: 'GRML', state: 'armed' });
    const flag = row({ symbol: 'GRML', setup_type: 'bull_flag', state: 'near' });
    const other = row({ symbol: 'IMCC', state: 'leg' });
    const by = rowsBySymbol([fp, other, flag]);
    expect(by.get('GRML')?.map(r => r.setup_type)).toEqual(['bull_flag', 'first_pullback']);
    expect(otherSetups(fp, [fp, other, flag])).toEqual(['bull_flag']);
    expect(signedPct(0)).toBe('0.0%');
    expect(signedPct(null)).toBe('');
  });
});

describe('the tape flow line (ADR 034)', () => {
  it('says the score, the label and each reading, and an unknown one as unknown', () => {
    expect(flowLine({ score: -0.62, label: 'flush', readings: { imbalance: -1, pace: -0.5, drift: -0.2, book: null } }))
      .toBe('Flow −0.62: a flush of selling (ask vs bid −1.00 · pace −0.50 · price move −0.20 · book unknown).');
    expect(flowLine({ score: null, label: 'blind' })).toMatch(/^Flow: no tape and no book/);
    expect(flowLine(null)).toBe('');
  });

  it('rides on the tape chip after the gate numbers', () => {
    const tape = tapeWords(row({ tape: { verdict: 'go', reasons: ['green on the tape'],
      flow: { score: 0.71, label: 'burst', readings: { imbalance: 0.9, pace: 1, drift: 0.4, book: 0.1 } } } }));
    expect(tape?.tip.split('\n').at(-1)).toMatch(/^Flow \+0\.71: a burst of buying/);
  });
});