import { describe, expect, it } from 'vitest';
import { formatSpikeAge, volumeBoostEmptyCopy } from './formatAge';

describe('formatSpikeAge', () => {
  it('formats seconds minutes and hours', () => {
    expect(formatSpikeAge(12)).toBe('12s ago');
    expect(formatSpikeAge(74)).toBe('1m ago');
    expect(formatSpikeAge(3600)).toBe('1h ago');
    expect(formatSpikeAge(null)).toBe('--');
  });
});

describe('volumeBoostEmptyCopy', () => {
  it('prefers feed error then unavailable then honest empty', () => {
    expect(volumeBoostEmptyCopy({ feedError: 'down' })).toBe('down');
    expect(volumeBoostEmptyCopy({ tableState: 'unavailable' })).toMatch(/IBKR is not ready/);
    expect(volumeBoostEmptyCopy({})).toMatch(/No exceptional volume-rate spikes/);
  });
});
