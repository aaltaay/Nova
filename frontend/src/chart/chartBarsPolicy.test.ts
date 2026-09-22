import { describe, expect, it } from 'vitest';
import {
  allowMockBarsFallback,
  CHART_EMPTY_NO_REPLAY,
  CHART_EMPTY_REPLAY_LOADING,
  CHART_EMPTY_REPLAY_TIME,
  chartEmptyText,
  emptyBarsMessage,
} from './chartBarsPolicy';

describe('chartBarsPolicy', () => {
  it('forbids mock bars when discovery is ibkr', () => {
    expect(allowMockBarsFallback('ibkr')).toBe(false);
    expect(emptyBarsMessage('ibkr')).toMatch(/IBKR/);
  });

  it('allows mock bars when discovery is alpaca', () => {
    expect(allowMockBarsFallback('alpaca')).toBe(true);
    expect(emptyBarsMessage('alpaca')).toMatch(/No chart bars/);
  });

  it('states why a pane is empty, and never blames a replay time with nothing loaded (QA V9)', () => {
    expect(chartEmptyText(true, { kind: 'none' }, 'ibkr')).toBe(CHART_EMPTY_NO_REPLAY);
    expect(chartEmptyText(true, { kind: 'none' }, 'ibkr')).not.toMatch(/replay time/);
    expect(chartEmptyText(true, { kind: 'ok' }, 'ibkr')).toBe(CHART_EMPTY_REPLAY_TIME);
    expect(chartEmptyText(true, { kind: 'other-symbol', replaySymbol: 'GRML' }, 'ibkr')).toMatch(/^GRML is the loaded replay/);
    expect(chartEmptyText(true, { kind: 'failed', error: 'x' }, 'ibkr')).toMatch(/did not load/);
    // A capture still being read from disk is neither loaded nor failed (#450's `loading`).
    expect(chartEmptyText(true, { kind: 'loading' }, 'ibkr')).toBe(CHART_EMPTY_REPLAY_LOADING);
    // At the live edge and off Sim the pane is live: the feed's own words.
    expect(chartEmptyText(true, { kind: 'live-edge' }, 'ibkr')).toBe(emptyBarsMessage('ibkr'));
    expect(chartEmptyText(false, { kind: 'ok' }, 'ibkr')).toBe(emptyBarsMessage('ibkr'));
  });
});
