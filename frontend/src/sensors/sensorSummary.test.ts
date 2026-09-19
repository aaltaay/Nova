import { describe, expect, it } from 'vitest';
import { SENSORS_NO_VALUE } from '../constantGroups/sensors';
import { sensorSummary } from './sensorSummary';
import type { SensorEnvelope } from './types';

function row(sensor: string, data: Record<string, unknown>, error?: string): SensorEnvelope {
  return { sensor, status: 'live', as_of: 1, data, error };
}

describe('sensorSummary', () => {
  it('prefers a loud error over a value', () => {
    expect(sensorSummary(row('tape', { print_count: 9 }, 'No prints yet'))).toBe('No prints yet');
  });

  it('summarizes live L2 and stub memory', () => {
    expect(sensorSummary(row('l2', { imbalance: 0.8, spread_ticks: 2 }))).toContain('imb 0.80');
    expect(sensorSummary({ ...row('memory', { count: 3 }), status: 'stub' })).toBe('3 decisions');
  });

  it('shows empty reading when data is missing', () => {
    expect(sensorSummary(row('vwap', {}))).toBe(SENSORS_NO_VALUE);
    expect(sensorSummary(row('tape', {}))).toBe(SENSORS_NO_VALUE);
    expect(sensorSummary(row('flow', {}))).toBe(SENSORS_NO_VALUE);
  });

  it('names Advice as the news source', () => {
    expect(sensorSummary(row('news', { source: 'advice', headline: 'Contract win' }))).toBe(
      'Advice · Contract win',
    );
    expect(sensorSummary(row('news', { source: 'advice' }))).toBe(`Advice · ${SENSORS_NO_VALUE}`);
  });

  it('labels halt and session phase', () => {
    expect(sensorSummary(row('halt', { halted: false }))).toBe('not halted');
    expect(sensorSummary(row('halt', { halted: true, kind: 'LULD' }))).toBe('HALT LULD');
    expect(sensorSummary(row('session-phase', { phase: 'power hour' }))).toBe('power hour');
  });

  it('summarizes every sensor key without unicode dashes', () => {
    const samples: Array<[string, Record<string, unknown>, string]> = [
      ['tape', { print_count: 4 }, '4 prints'],
      ['macd', { ready: true, macd: 0.12, histogram: 0.01 }, 'MACD 0.120'],
      ['rvol', { rvol_vs_adv_pace: 1.5 }, 'pace 1.50'],
      ['day-volume', { day_volume: 900 }, '900'],
      ['spread', { spread_ticks: 2, direction: 'widening' }, '2.0t widening'],
      ['flow', { sweep: { side: 'ask' } }, 'sweep yes'],
      ['last-move', { seconds_ago: 12 }, '12s ago'],
      ['liquidity', { adv: 1000 }, 'ADV 1000'],
      ['emas', { ema_9: { value: 10.5 } }, 'EMA9 10.500'],
      ['news', { source: 'advice', headline: 'Contract win' }, 'Advice · Contract win'],
      ['risk', { daily_loss_limit_remaining: 400, consecutive_losses: 1 }, 'remain 400'],
      ['regime', { regime: 'chopping', confidence: 0.4 }, 'chopping (0.40)'],
      ['macro', { count: 3 }, '3 stub events'],
    ];
    for (const [sensor, data, needle] of samples) {
      const text = sensorSummary(row(sensor, data));
      expect(text).toContain(needle);
      expect(text).not.toContain('\u2014');
      expect(text).not.toContain('\u2013');
    }
  });
});
