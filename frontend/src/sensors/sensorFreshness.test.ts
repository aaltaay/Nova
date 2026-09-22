import { describe, expect, it } from 'vitest';
import { humanAge, sensorBarsStaleLabel } from './sensorFreshness';
import { sensorChipStatus } from './SensorStatusChip';
import { sensorSummary } from './sensorSummary';

// 2026-09-15 10:10 ET, the week-old AAPL bar the QA pass saw (W16).
const WEEK_OLD_BAR = Date.parse('2026-09-15T14:10:00Z') / 1000;
const NOW = Date.parse('2026-09-22T09:22:19Z') / 1000;

describe('sensor freshness (QA W16)', () => {
  it('names a stale bar set in ET and leaves a fresh one alone', () => {
    expect(sensorBarsStaleLabel({ data: { bars_as_of: WEEK_OLD_BAR } }, NOW)).toBe('Sep 15, 10:10');
    expect(sensorBarsStaleLabel({ data: { bars_as_of: NOW - 60 } }, NOW)).toBeNull();
    expect(sensorBarsStaleLabel({ data: {} }, NOW)).toBeNull();
    expect(sensorBarsStaleLabel({ data: { bars_as_of: 'x' } }, NOW)).toBeNull();
  });

  it('turns a live chip stale, never a stub or an error', () => {
    expect(sensorChipStatus({ status: 'live' }, 'Sep 15, 10:10')).toBe('stale');
    expect(sensorChipStatus({ status: 'live' }, null)).toBe('live');
    expect(sensorChipStatus({ status: 'stub' }, 'Sep 15, 10:10')).toBe('stub');
    expect(sensorChipStatus({ status: 'live', error: 'boom' }, 'Sep 15, 10:10')).toBe('error');
  });

  it('writes ages in days / hours / minutes, not raw seconds', () => {
    expect(humanAge(45)).toBe('45s');
    expect(humanAge(185)).toBe('3m 5s');
    expect(humanAge(4 * 3600 + 12 * 60)).toBe('4h 12m');
    expect(humanAge(587539.305)).toBe('6d 19h');
    expect(sensorSummary({ sensor: 'last-move', status: 'live', as_of: 1, data: { seconds_ago: 587539.305 } }))
      .toBe('6d 19h ago');
  });
});
