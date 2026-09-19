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
  });

  it('labels halt and session phase', () => {
    expect(sensorSummary(row('halt', { halted: false }))).toBe('not halted');
    expect(sensorSummary(row('halt', { halted: true, kind: 'LULD' }))).toBe('HALT LULD');
    expect(sensorSummary(row('session-phase', { phase: 'power hour' }))).toBe('power hour');
  });
});
