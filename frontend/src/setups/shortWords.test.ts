import { describe, expect, it } from 'vitest';
import { gradeWords } from './pillarWords';
import { distanceLabel } from './setupsFormat';
import { stateWords, tapeWords, toGoWords, triggerWords } from './setupWords';
import type { SetupRow } from './types';

/** A bear flag armed under 5.40, its buy stop 5.53 over the flag, its cover 5.13 (2R under the entry). */
function short(partial: Partial<SetupRow> = {}): SetupRow {
  return {
    symbol: 'FADE', setup_type: 'bear_flag', side: 'short', ssr: 'off', state: 'armed',
    reason: 'flag of 2 over the 5.20 pole: short under 5.40, buy stop 5.53, risk 0.14', kind: 'bear_flag', nth: 0,
    setup_id: 'f1',
    setup: { trigger: 5.40, entry: 5.39, stop: 5.53, risk: 0.14, target1: 5.11, pullback_bars: 2, leg_high: 5.6,
      leg_low: 5.2, leg_pct: 0.071, detail: { flag_bars: 2, pole_bars: 3 } },
    leg: { t: 0, high: 5.6, low: 5.2, pct: 0.071, bars: 3 }, last_price: 5.44, distance: 0.04, grade: 'B', pillars: null,
    tape: null, proposal: null, outcome: null, bar_r: null, mfe: null, mae: null,
    ...partial,
  };
}

describe('a short setup in its own words (ADR 049)', () => {
  it('says its states the short way: a pole down, a flag, broke down', () => {
    expect(stateWords(short({ state: 'leg', setup: null })).text).toBe('Pole down · 3 red');
    expect(stateWords(short()).text).toBe('Flag · 2 bars');
    const fade = short({ setup_type: 'backside_lower_high', state: 'leg', setup: null,
      leg: { t: 0, high: 6.01, low: 5.46, pct: 0.092 } });
    expect(stateWords(fade).text).toBe('Fading −9.2%');
    expect(stateWords(fade).tip).toMatch(/Fade −9\.2% off the 6\.01 high of day, to 5\.46\./);
    expect(stateWords(short()).tip).toMatch(/Trigger 5\.40 · short 5\.39 · buy stop 5\.53 · risk 14¢ a share · cover 1 5\.11/);
  });

  it('puts its trigger under the price: trading under it starts the short, the buy stop over it', () => {
    const tip = triggerWords(short()).tip;
    expect(tip).toMatch(/Trigger 5\.40: the last flag candle's low\. Trading under it starts the short\./);
    expect(tip).toMatch(/Entry 5\.39 \(the trigger −1c, the short's limit\)\./);
    expect(tip).toMatch(/Buy stop 5\.53: 1c over the flag\./);
    expect(tip).toMatch(/Cover 1 5\.11: R x the risk under the entry\./);
  });

  it('counts the distance over the trigger; the SSR bounce rests over the price, so its distance is under', () => {
    expect(distanceLabel(short())).toBe('4¢ over');
    expect(toGoWords(short()).tip).toMatch(/^4¢ over the 5\.40 trigger/);
    const bounce = short({ setup_type: 'ssr_bounce', ssr: 'on',
      setup: { ...short().setup!, trigger: 4.99, entry: 4.99, stop: 5.09, detail: { level: 5.0, level_kind: 'round' } } });
    expect(distanceLabel(bounce)).toBe('4¢ under');
    expect(toGoWords(bounce).tip).toMatch(/^4¢ under the resting short at 4\.99/);
    expect(stateWords(bounce).text).toBe('Resting under 5.00');
  });

  it('reads the tape the mirror way, and scores the short as a cover', () => {
    const tape = tapeWords(short({ tape: { verdict: 'wait', reasons: ['25k-share buyer at 5.40 is not thinning'],
      metrics: { wall_size: 25000, wall_price: 5.40 } } }));
    expect(tape?.tip).toMatch(/^WAIT: not yet\. A buyer at the level that is not thinning/);
    expect(tape?.tip).toMatch(/biggest buyer at the level 25k at 5\.40/);
    const won = stateWords(short({ state: 'triggered', outcome: 'target_first', bar_r: 1.8,
      setup: { ...short().setup!, triggered_at: 0 } }));
    expect(won.tip).toMatch(/So far: the cover first \(\+1\.80R\)\./);
  });

  it('grades a short by its own pillars: the run, the fade, VWAP, bad news and borrow', () => {
    const graded = gradeWords(short({ pillars: {
      price: 5.44, change_pct: null, rvol: null, float: null, news: null, headline: null,
      run_pct: 50.2, fade_pct: 9.4, vwap: 5.71,
      bad_news: { dilution: true, negative: false, text: null },
      borrow: { shares: 20000, order_shares: 357 },
      checks: { run: true, fade: true, vwap: true, bad_news: true, borrow: true },
    } }));
    expect(graded.text).toBe('B 5/5');
    expect(graded.tip).toMatch(/✓ Ran 30%\+ today: high of day \+50% over the prior close/);
    expect(graded.tip).toMatch(/✓ Under VWAP: 5\.44 vs VWAP 5\.71/);
    expect(graded.tip).toMatch(/✓ Dilution or bad news on file: dilution on file/);
    expect(graded.tip).toMatch(/✓ Borrow at least 10x the order: 20,000 shortable for a 357-share order/);
    expect(graded.tip).not.toMatch(/Catalyst:/);
  });
});
