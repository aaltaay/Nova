import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import {
  etMinutesFromChartTime,
  sessionColorForChartTime,
  sessionKindFromEtMinutes,
  sessionKindForChartTime,
  supportsSessionHighlight,
} from './sessionHighlight';
import { CHART_SESSION_COLORS } from '../constants';

/** Build an ET-encoded chart timestamp (same convention as isoToEtTime). */
function etTime(hour: number, minute: number): Time {
  // 2026-07-16 as a neutral weekday; values are read via getUTC*.
  return (Date.UTC(2026, 6, 16, hour, minute, 0) / 1000) as Time;
}

describe('sessionHighlight', () => {
  it('enables only intraday timeframes', () => {
    expect(supportsSessionHighlight('1Min')).toBe(true);
    expect(supportsSessionHighlight('5Min')).toBe(true);
    expect(supportsSessionHighlight('15Min')).toBe(true);
    expect(supportsSessionHighlight('1Hour')).toBe(true);
    expect(supportsSessionHighlight('1Day')).toBe(false);
    expect(supportsSessionHighlight('1Week')).toBe(false);
  });

  it('classifies ET minutes into premarket / RTH / after-hours / closed', () => {
    expect(sessionKindFromEtMinutes(4 * 60)).toBe('premarket');
    expect(sessionKindFromEtMinutes(9 * 60 + 29)).toBe('premarket');
    expect(sessionKindFromEtMinutes(9 * 60 + 30)).toBe('rth');
    expect(sessionKindFromEtMinutes(15 * 60 + 59)).toBe('rth');
    expect(sessionKindFromEtMinutes(16 * 60)).toBe('afterhours');
    expect(sessionKindFromEtMinutes(19 * 60 + 59)).toBe('afterhours');
    expect(sessionKindFromEtMinutes(20 * 60)).toBe('closed');
    expect(sessionKindFromEtMinutes(2 * 60)).toBe('closed');
  });

  it('reads ET wall clock from chart timestamps', () => {
    expect(etMinutesFromChartTime(etTime(9, 30))).toBe(9 * 60 + 30);
    expect(sessionKindForChartTime(etTime(7, 15))).toBe('premarket');
    expect(sessionKindForChartTime(etTime(10, 0))).toBe('rth');
    expect(sessionKindForChartTime(etTime(17, 0))).toBe('afterhours');
    expect(sessionColorForChartTime(etTime(7, 0))).toBe(CHART_SESSION_COLORS.premarket);
    expect(sessionColorForChartTime(etTime(11, 0))).toBe(CHART_SESSION_COLORS.rth);
    expect(sessionColorForChartTime(etTime(18, 0))).toBe(CHART_SESSION_COLORS.afterhours);
  });
});
