import { describe, expect, it } from 'vitest';
import { TickMarkType, type Time } from 'lightweight-charts';
import { formatChartCrosshairTime, formatChartTickMark } from './chartTimeFormat';

describe('chartTimeFormat AM/PM', () => {
  // 2026-07-23 17:02 ET encoded as UTC seconds (matches isoToEtTime encoding).
  const seventeenOhTwo = Date.UTC(2026, 6, 23, 17, 2, 0) / 1000;

  it('formats crosshair time with AM/PM (library-style date + 12h clock)', () => {
    expect(formatChartCrosshairTime(seventeenOhTwo as Time)).toBe("23 Jul '26 5:02 PM");
  });

  it('formats morning crosshair with AM', () => {
    const nineThirty = Date.UTC(2026, 6, 23, 9, 30, 0) / 1000;
    expect(formatChartCrosshairTime(nineThirty as Time)).toBe("23 Jul '26 9:30 AM");
  });

  it('formats Time tick marks with AM/PM (not 24h)', () => {
    expect(formatChartTickMark(seventeenOhTwo as Time, TickMarkType.Time, 'en-US')).toBe(
      '5:02 PM',
    );
  });

  it('formats noon and midnight without 24h clock', () => {
    const noon = Date.UTC(2026, 6, 23, 12, 0, 0) / 1000;
    const midnight = Date.UTC(2026, 6, 23, 0, 0, 0) / 1000;
    expect(formatChartTickMark(noon as Time, TickMarkType.Time, 'en-US')).toBe('12:00 PM');
    expect(formatChartTickMark(midnight as Time, TickMarkType.Time, 'en-US')).toBe('12:00 AM');
  });
});
