/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  buildSampleDashboardUrl,
  buildSampleTraderUrl,
  isSampleView,
  parseSampleSymbol,
  SAMPLE_VIEW_QUERY_VALUE,
} from './sampleNav';

describe('sampleNav', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('detects sample view and never treats stock view as sample', () => {
    expect(isSampleView('?view=sample')).toBe(true);
    expect(isSampleView('?view=stock&symbol=AAPL')).toBe(false);
    expect(isSampleView('')).toBe(false);
  });

  it('parses sample trader symbol only on sample route', () => {
    expect(parseSampleSymbol('?view=sample&symbol=smpl')).toBe('SMPL');
    expect(parseSampleSymbol('?view=stock&symbol=SMPL')).toBeNull();
    expect(parseSampleSymbol('?view=sample')).toBeNull();
  });

  it('builds isolated sample URLs', () => {
    const dash = buildSampleDashboardUrl('http://localhost:5173/?view=stock&symbol=X');
    expect(dash).toContain(`view=${SAMPLE_VIEW_QUERY_VALUE}`);
    expect(dash).not.toContain('symbol=');

    const trader = buildSampleTraderUrl('gapx', 'http://localhost:5173/');
    expect(trader).toContain('view=sample');
    expect(trader).toContain('symbol=GAPX');
  });
});
