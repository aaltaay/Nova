/**
 * The Performance curve plots the selected range and ends at the live mark
 * (QA W13 / W1), with axis labels that carry cents when the range is small
 * (W26). Before: a 1D chart plotted P&L since the ledger opened (-$1, Sep 21's
 * -$0.53 rounded to a dollar) under a $0.00 headline, and ended at +$14.74
 * (positions at their last fill) under +$20.48 / Day's +$28.40.
 */
import { describe, expect, it } from 'vitest';
import type { PracticeHistory } from './accountHistoryTypes';
import { lineGeometry, rangeSeries, tickDecimals } from './equityPath';
import { perfTick } from './PerformancePanel';

const T0 = 1_790_000_000;

function history(over: Partial<PracticeHistory>): PracticeHistory {
  return {
    venue: 'paper', account_id: 'NOVA-PAPER', range: '1D', range_start: T0, schema_version: 1,
    starting_cash: 100_000, ledger_opened_at: null, equity: [], fills: [], by_source: [], daily: [],
    archives: [], components: { realized: 0, unrealized: 0, commissions: 0, sec_finra_fees: 0, bot_realized: 0 },
    warnings: [], ...over,
  };
}

describe('rangeSeries', () => {
  it('a flat new day after a losing day plots $0.00 from the rollover, not the ledger lifetime', () => {
    // Sep 21 lost $0.53; Sep 22's rollover carries realized -0.53, no position.
    const h = history({
      equity: [{ ts: T0, net_liquidation: 99_999.47, cash: 99_999.47, realized: -0.53, unrealized: 0 }],
    });
    const { series, baseline } = rangeSeries(h, 'pnl', { openPnl: 0, netLiquidation: 99_999.47 }, T0 + 3_600);
    expect(series.map((p) => p.value)).toEqual([0, 0]);
    expect(baseline).toBe(0);
  });

  it('ends at realized + the live open P&L -- the headline and Day\'s P&L', () => {
    const h = history({
      components: { realized: 8.4774, unrealized: 12, commissions: 3, sec_finra_fees: 0.02, bot_realized: 0 },
      equity: [
        { ts: T0, net_liquidation: 99_990, cash: 99_990, realized: -10, unrealized: 0 },
        { ts: T0 + 60, net_liquidation: 100_010.4774, cash: 99_500, realized: -1.5226, unrealized: 12 },
      ],
    });
    const now = T0 + 600;
    const { series } = rangeSeries(h, 'pnl', { openPnl: 19.92, netLiquidation: 100_018.3974 }, now);
    expect(series[0].value).toBeCloseTo(0, 6);
    expect(series[1].value).toBeCloseTo(8.4774 + 12, 6); // event-marked in between
    expect(series[2]).toEqual({ ts: now, value: expect.closeTo(8.4774 + 19.92, 6) });
  });

  it('value mode ends at the live net liquidation over the value the range began from', () => {
    const h = history({
      components: { realized: 5, unrealized: 0, commissions: 1, sec_finra_fees: 0, bot_realized: 0 },
      equity: [{ ts: T0, net_liquidation: 100_020, cash: 100_020, realized: 20, unrealized: 0 }],
    });
    const { series, baseline } = rangeSeries(h, 'value', { openPnl: 2, netLiquidation: 100_022 }, T0 + 10);
    expect(series.at(-1)).toEqual({ ts: T0 + 10, value: 100_022 });
    expect(baseline).toBe(100_015); // starting cash + what was realized before the range
  });

  it('P&L % is over that same range base', () => {
    const h = history({
      components: { realized: 5, unrealized: 0, commissions: 1, sec_finra_fees: 0, bot_realized: 0 },
      equity: [{ ts: T0, net_liquidation: 100_020, cash: 100_020, realized: 20, unrealized: 0 }],
    });
    const { series } = rangeSeries(h, 'pct', { openPnl: 2, netLiquidation: 100_022 }, T0 + 10);
    expect(series.at(-1)!.value).toBeCloseTo((7 / 100_015) * 100, 9);
  });

  it('without a live mark the curve stops at the last event instead of guessing one', () => {
    const h = history({ equity: [{ ts: T0, net_liquidation: 100_000, cash: 100_000, realized: 0, unrealized: 0 }] });
    expect(rangeSeries(h, 'pnl', { openPnl: null, netLiquidation: null }, T0 + 10).series).toHaveLength(1);
  });
});

describe('axis labels', () => {
  it('carry cents while the ticks are closer than a dollar and never repeat', () => {
    const geo = lineGeometry(
      [{ ts: T0, value: 0 }, { ts: T0 + 60, value: -0.53 }],
      { width: 400, height: 150, padLeft: 56, padRight: 10, padTop: 12, padBottom: 6 },
      0,
    );
    expect(geo.step).toBeLessThan(1);
    const labels = geo.ticks.map((t) => perfTick('pnl', t.value, geo.step));
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels.every((l) => /\.\d\d$/.test(l))).toBe(true);
  });

  it('decimals follow the step', () => {
    expect(tickDecimals(5, 'money')).toBe(0);
    expect(tickDecimals(0.2, 'money')).toBe(2);
    expect(tickDecimals(0.2, 'pct')).toBe(1);
    expect(tickDecimals(0.005, 'pct')).toBe(3);
    expect(perfTick('value', 100_014.2, 0.5)).toBe('100,014.20');
    expect(perfTick('value', 100_014, 5)).toBe('100,014');
  });
});
