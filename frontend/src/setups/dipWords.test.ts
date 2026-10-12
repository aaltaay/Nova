import { describe, expect, it } from 'vitest';
import { isWatchOnlySetup } from '../constantGroups/bot';
import { onLockOf } from '../bot/botLevels';
import { statusOf } from '../bot/strategyBuckets';
import { ruleLines, ruleSummary } from '../bot/templateFormat';
import fixture from '../bot/setupTemplatesFixture.json';
import { dipCandleWords, isDip } from './dipWords';
import { funnelSteps, stateWords, triggerWords } from './setupWords';
import type { SetupLevels, SetupRow } from './types';

const BOUGHT: SetupLevels = {
  trigger: 4.32, entry: 4.33, stop: 4.23, risk: 0.1, target1: 4.39, target2: 4.49, target1_fraction: 0.5,
  pullback_bars: 2, leg_high: 4.39, leg_low: 3.99, leg_pct: 0.1003, triggered_at: 1_789_995_960,
  targets: { first: { kind: 'pullback_high', price: 4.39, why: 'the pullback high 4.39' },
    second: { kind: 'next_level', price: 4.49, why: '1c under $4.50' }, hod: 4.39, pullback_high: 4.39, stop: null,
    rule: { first: 'pullback_high', second: 'hod_or_level', fixed: 0.2, split: 0.5, stop: 'pattern' } },
  detail: { entry_mode: 'wick', entry_bar_t: 1_789_995_900, lower_wick: 0.07, wick_pct: 0.7778, close_pct: 0.8889,
    red_bars: 1, pullback_low: 4.24, pullback_high: 4.39 },
};

function row(partial: Partial<SetupRow> = {}): SetupRow {
  return {
    symbol: 'ABCD', setup_type: 'pullback_dip', state: 'triggered', reason: 'bought the dip at the 4.32 close',
    kind: 'pullback_dip', nth: 1, setup_id: 's1', setup: BOUGHT, leg: { t: 0, high: 4.39, low: 3.99, pct: 0.1003 },
    last_price: 4.35, distance: null, grade: 'A', pillars: null, tape: null, proposal: null, outcome: null,
    bar_r: null, mfe: null, mae: null, ...partial,
  };
}

const DIP_VALUES = (fixture.setups.find(s => s.id === 'pullback_dip')!.templates[0].values) as Record<string, never>;

describe('the pullback dip in words (#847, watch only)', () => {
  it('its "trigger" is the close it bought, with the candle, the stop under the pullback low and the targets', () => {
    expect(isDip(row())).toBe(true);
    const w = triggerWords(row());
    expect(w.text).toBe('4.32');
    expect(w.title).toBe('Dip close · Pullback dip');
    expect(w.tip).toContain('Bought the dip at the 4.32 close of the candle that bottomed the pullback: a bottoming '
      + 'wick (7¢ of lower wick, 78% of the candle, closing 89% up it).');
    expect(w.tip).toContain('Entry 4.33 (the close +1c');
    expect(w.tip).toContain('Stop 4.23: under the pullback\'s low 4.24.');
    expect(w.tip).toContain('Target 1 4.39 (the pullback high 4.39)');
    expect(w.tip).toContain('Watch only');
  });

  it('says its states in its own words', () => {
    expect(stateWords(row({ state: 'pullback', setup: null })).text).toBe('Dipping');
    expect(stateWords(row()).text).toMatch(/^Bought the dip \d\d:\d\d$/);
    expect(stateWords(row()).tip).toContain('Run +10.0% to 4.39 (from 3.99), then a pullback of 2 candles.');
    expect(stateWords(row()).tip).toContain('Bought at the 4.32 close · entry 4.33 · stop 4.23');
    expect(funnelSteps('pullback_dip', { watching: 3, forming: 1, armed: 2, near: 0, triggered: 2, failed: 0,
      proposed: 0, filtered: 0 }).map(s => s.word).slice(0, 4)).toEqual(['dipping', 'bottomed', 'near', 'bought the dip']);
  });

  it('names a green entry by its red candles', () => {
    expect(dipCandleWords({ detail: { entry_mode: 'green', red_bars: 2 } })).toBe('the first green close after 2 red candles');
  });

  it('reads its template: the run, the entry candle, the stop and "watch only", never a bot window', () => {
    const lines = Object.fromEntries(ruleLines('pullback_dip', DIP_VALUES));
    expect(lines.Setup).toContain('Leg ≥ 5% to a new high of day · a 2–4 candle pullback (the entry candle included)');
    expect(lines.Entry).toBe('A bottoming wick (lower wick ≥ 50% of the candle and $0.02, closing ≥ 60% up it), at its '
      + 'close +$0.01 · arms 07:00–11:30');
    expect(lines.Trade).toContain('Stop $0.01 under the pullback\'s low');
    expect(lines.Trade).toContain('target 1 the pullback high');
    expect(lines.Trade).toContain('watch only: scored, never traded');
    expect(lines.Trade).not.toContain('bot ');
    expect(ruleLines('pullback_dip', { ...DIP_VALUES, dip_entry: 'green' as never })[2][1])
      .toMatch(/^The first green close after 1\+ red, at its close/);
    expect(ruleSummary('pullback_dip', DIP_VALUES)).toBe(
      'Bottoming wick in a 2–4 candle pullback off a 5%+ leg · stop under the pullback low · watch only');
  });

  it('locks its On for good, in the backend\'s words when it sends them', () => {
    expect(isWatchOnlySetup('pullback_dip')).toBe(true);
    expect(isWatchOnlySetup('first_pullback')).toBe(false);
    expect(onLockOf('pullback_dip', 'long', 'On is locked: watch only')).toBe('On is locked: watch only');
    expect(onLockOf('pullback_dip', 'long', null)).toMatch(/^On is locked/);
    expect(onLockOf('first_pullback', 'long', 'x')).toBeNull();
    expect(onLockOf('bear_flag', 'short', 'test queued')).toBe('test queued');
    const status = statusOf({ id: 'pullback_dip', label: 'Pullback dip', side: 'long', own: 1, locked: 'x', test: null,
      readout: null });
    expect(status.text).toMatch(/^Watch only · /);
    expect(status.tip).toContain('never trades it');
  });
});
