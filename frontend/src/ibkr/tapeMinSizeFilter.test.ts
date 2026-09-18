/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { PREF_SCHEMA_VERSION } from '../utils/prefStore';
import { TAPE_MIN_SIZE_STORAGE_KEY } from '../constants';
import {
  applyTapeMinSizeDraft,
  filterTapePrints,
  parseTapeMinSize,
  readTapeMinSize,
  tapeFilterMenuPosition,
  tapeMinSizeBadgeLabel,
  tapeMinSizeEmptyLabel,
  writeTapeMinSize,
} from './tapeMinSizeFilter';

describe('parseTapeMinSize / applyTapeMinSizeDraft', () => {
  it('treats empty, 0, and whitespace as show-all', () => {
    expect(parseTapeMinSize('')).toBe(0);
    expect(parseTapeMinSize('   ')).toBe(0);
    expect(parseTapeMinSize('0')).toBe(0);
    expect(parseTapeMinSize(0)).toBe(0);
    expect(applyTapeMinSizeDraft('')).toBe(0);
  });

  it('parses a whole-number min size', () => {
    expect(parseTapeMinSize('100')).toBe(100);
    expect(parseTapeMinSize(100.9)).toBe(100);
    expect(applyTapeMinSizeDraft(' 250 ')).toBe(250);
  });

  it('ignores incomplete drafts so typing does not reset the filter', () => {
    expect(applyTapeMinSizeDraft('12a')).toBeNull();
    expect(parseTapeMinSize('10.5')).toBeNull();
    expect(parseTapeMinSize(-4)).toBe(0);
  });
});

describe('filterTapePrints', () => {
  const prints = [
    { size: 10 },
    { size: 50 },
    { size: 100 },
    { size: 500 },
  ];

  it('returns every print when min size is 0', () => {
    expect(filterTapePrints(prints, 0)).toEqual(prints);
  });

  it('hides prints smaller than the min size', () => {
    expect(filterTapePrints(prints, 100).map((p) => p.size)).toEqual([100, 500]);
  });

  it('does not mutate the ring', () => {
    const copy = prints.slice();
    filterTapePrints(prints, 100);
    expect(prints).toEqual(copy);
  });
});

describe('tapeMinSizeBadgeLabel', () => {
  it('is hidden when inactive and obvious when active', () => {
    expect(tapeMinSizeBadgeLabel(0)).toBeNull();
    expect(tapeMinSizeBadgeLabel(100)).toBe('Size ≥ 100');
    expect(tapeMinSizeEmptyLabel(100)).toBe('No prints Size ≥ 100');
  });
});

describe('tape min size localStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('round-trips through the prefStore envelope', () => {
    writeTapeMinSize(100);
    const stored = JSON.parse(localStorage.getItem(TAPE_MIN_SIZE_STORAGE_KEY) ?? '');
    expect(stored.schema_version).toBe(PREF_SCHEMA_VERSION);
    expect(stored.value).toBe(100);
    expect(readTapeMinSize()).toBe(100);

    writeTapeMinSize(0);
    expect(readTapeMinSize()).toBe(0);
  });

  it('refuses an unknown schema_version', () => {
    localStorage.setItem(
      TAPE_MIN_SIZE_STORAGE_KEY,
      JSON.stringify({ schema_version: 99, value: 999 }),
    );
    expect(readTapeMinSize()).toBe(0);
  });
});

describe('tapeFilterMenuPosition', () => {
  it('keeps the panel inside the viewport', () => {
    const pos = tapeFilterMenuPosition({
      x: 900,
      y: 700,
      menuWidth: 220,
      menuHeight: 104,
      viewportWidth: 1000,
      viewportHeight: 800,
    });
    expect(pos.left + 220).toBeLessThanOrEqual(1000);
    expect(pos.top + 104).toBeLessThanOrEqual(800);
  });
});
