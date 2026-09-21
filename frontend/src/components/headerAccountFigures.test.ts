import { describe, expect, it } from 'vitest';
import { PAPER_ACCOUNT as PAPER } from '../practice/practiceFixtures';
import {
  dayPnlPercent,
  figuresFromPractice,
  figuresFromSummary,
  headerMoney,
} from './headerAccountFigures';

describe('figuresFromSummary (Live: the IBKR account)', () => {
  it("reads the summary and sums Day's from realized + unrealized", () => {
    const f = figuresFromSummary({
      connected: true,
      mode: 'live',
      NetLiquidation: 3559.55,
      TotalCashValue: 3558.53,
      BuyingPower: 7117.06,
      UnrealizedPnL: -0.17,
      RealizedPnL: 12.5,
      GrossPositionValue: 1.02,
      ExcessLiquidity: 3000,
    });
    expect(f.source).toBe('ibkr');
    expect(f.dayPnl).toBeCloseTo(12.33);
    expect(f.openPnl).toBe(-0.17);
    expect(f.realizedPnl).toBe(12.5);
    expect(f.netLiquidation).toBe(3559.55);
    expect(f.cash).toBe(3558.53);
    expect(f.buyingPower).toBe(7117.06);
    expect(f.excessLiquidity).toBe(3000);
    expect(f.grossPositionValue).toBe(1.02);
    expect(f.feesToday).toBeNull();
    expect(f.startingCash).toBeNull();
    expect(f.replayKey).toBeNull();
  });

  it('never fabricates: a missing summary or field is null, and Excess Liquidity stays absent', () => {
    const none = figuresFromSummary(null);
    expect(none.dayPnl).toBeNull();
    expect(none.netLiquidation).toBeNull();
    expect(none.excessLiquidity).toBeNull();
    const partial = figuresFromSummary({ connected: true, mode: 'live', NetLiquidation: Number.NaN });
    expect(partial.netLiquidation).toBeNull();
    expect(partial.excessLiquidity).toBeNull();
  });
});

describe('figuresFromPractice (Paper / Sim: Nova\'s ledger, ADR 020)', () => {
  it('reads the ledger with fees and starting cash, and no Excess Liquidity', () => {
    const f = figuresFromPractice(PAPER);
    expect(f.source).toBe('practice');
    expect(f.dayPnl).toBe(250.25);
    expect(f.openPnl).toBe(-100);
    expect(f.realizedPnl).toBe(350.25);
    expect(f.netLiquidation).toBe(101200.25);
    expect(f.cash).toBe(98750.5);
    expect(f.buyingPower).toBe(395002);
    expect(f.grossPositionValue).toBe(2449.75);
    expect(f.feesToday).toBe(3.5);
    expect(f.startingCash).toBe(100000);
    expect(f.excessLiquidity).toBeNull();
    expect(f.replayKey).toBeNull();
  });

  it('carries the Sim replay key, empty when Sim has nothing loaded, null on Paper', () => {
    const loaded = figuresFromPractice({
      ...PAPER,
      venue: 'sim',
      account_id: 'NOVA-SIM',
      replay_key: 'capture:AAPL:2026-09-19',
    });
    expect(loaded.replayKey).toBe('capture:AAPL:2026-09-19');
    const empty = figuresFromPractice({ ...PAPER, venue: 'sim', account_id: 'NOVA-SIM', replay_key: null });
    expect(empty.replayKey).toBe('');
    expect(figuresFromPractice(PAPER).replayKey).toBeNull();
  });

  it('renders a missing number as the placeholder, not as zero', () => {
    const f = figuresFromPractice({
      ...PAPER,
      cash: Number.NaN,
      buying_power: undefined as unknown as number,
      day_pnl: Number.NaN,
      realized_pnl: Number.NaN,
      unrealized_pnl: Number.NaN,
    });
    expect(f.cash).toBeNull();
    expect(f.buyingPower).toBeNull();
    expect(f.dayPnl).toBeNull();
    expect(headerMoney(f.cash)).toBe('--');
    expect(headerMoney(1234.5)).toBe('$1,234.50');
  });
});

describe('dayPnlPercent', () => {
  it("is Day's over the value the account started the day with", () => {
    // 250.25 / (101200.25 - 250.25) = 250.25 / 100950
    expect(dayPnlPercent(250.25, 101200.25)).toBeCloseTo(0.24789, 4);
    expect(dayPnlPercent(-0.17, 3559.55)).toBeCloseTo(-0.004776, 5);
    expect(dayPnlPercent(0, 1000)).toBe(0);
  });

  it('is left out when the base is not > 0 or a figure is missing', () => {
    expect(dayPnlPercent(10, 10)).toBeNull();
    expect(dayPnlPercent(100, 50)).toBeNull();
    expect(dayPnlPercent(0, 0)).toBeNull();
    expect(dayPnlPercent(null, 1000)).toBeNull();
    expect(dayPnlPercent(5, null)).toBeNull();
  });
});
