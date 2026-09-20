/**
 * @vitest-environment node
 * The sample account fixture is marketing chrome AND an #184 regression guard.
 */
import { describe, expect, it } from 'vitest';
import { SAMPLE_IBKR_ACCOUNT_STATE, SAMPLE_SUMMARY } from './sampleAccount';

describe('Nova Marketing Sample Data account', () => {
  it('stays a connected margin paper account (#184 short side)', () => {
    expect(SAMPLE_SUMMARY.connected).toBe(true);
    expect(SAMPLE_SUMMARY.mode).toBe('paper');
    // sample-shortability.spec.ts depends on both of these reaching the ticket.
    expect(SAMPLE_SUMMARY.AccountType).toBe('MARGIN');
    expect(SAMPLE_SUMMARY.account_class).toBe('margin');
  });

  it('carries present-and-zero RealizedPnL so Day P&L is not "--"', () => {
    // The exact distinction that made the header render a placeholder: absent
    // is not the same as zero (globalBarMoney.dayPnlFromSummary).
    expect(SAMPLE_SUMMARY.RealizedPnL).toBe(0);
    expect(SAMPLE_SUMMARY.UnrealizedPnL).toBe(230);
  });

  it('reconciles net liquidation with cash plus gross position value', () => {
    expect(SAMPLE_SUMMARY.NetLiquidation).toBe(100_000);
    expect(
      (SAMPLE_SUMMARY.TotalCashValue ?? 0) + (SAMPLE_SUMMARY.GrossPositionValue ?? 0),
    ).toBe(SAMPLE_SUMMARY.NetLiquidation);
  });

  it('reconciles the summary with the SMPL sample position', () => {
    const smpl = SAMPLE_IBKR_ACCOUNT_STATE.positions.find(p => p.symbol === 'SMPL');
    expect(smpl).toBeDefined();
    expect(SAMPLE_SUMMARY.GrossPositionValue).toBe(
      (smpl!.market_price ?? 0) * smpl!.qty,
    );
    expect(SAMPLE_SUMMARY.UnrealizedPnL).toBe(smpl!.unrealized_pnl);
    // Binary floating point: (4.25 - 3.10) * 200 is 229.99999999999997.
    expect(SAMPLE_SUMMARY.UnrealizedPnL).toBeCloseTo(
      ((smpl!.market_price ?? 0) - (smpl!.avg_cost ?? 0)) * smpl!.qty,
      6,
    );
  });
});
