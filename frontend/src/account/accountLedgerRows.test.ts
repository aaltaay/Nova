import { describe, expect, it } from 'vitest';
import { paperHistoryFixture } from './accountFixtures';
import { fillCashMovement, isoToTs, ledgerRows } from './accountLedgerRows';

describe('ledgerRows', () => {
  it('lists fills newest first with the cash movement and the balance the backend published', () => {
    const history = paperHistoryFixture(1_800_000_000);
    const rows = ledgerRows(history);
    const fills = rows.filter((r) => r.kind === 'fill');
    expect(fills).toHaveLength(6);
    expect(fills[0].fill!.order_id).toBe(6);
    expect(fills[5].fill!.order_id).toBe(1);
    // BUY 100 GRML @ 8.80, comm 1.00 -> -(880 + 1) ; balance = equity cash after that event.
    expect(fills[0].amount).toBeCloseTo(-881, 6);
    expect(fills[0].balance).toBe(96582.1);
    // SELL 500 GRML @ 5.35, comm 2.50, fees 0.20 -> +(2675 - 2.7).
    expect(fills[4].amount).toBeCloseTo(2672.3, 6);
    expect(fills[4].balance).toBe(100119.8);
    for (let i = 1; i < rows.length; i++) expect(rows[i - 1].ts).toBeGreaterThanOrEqual(rows[i].ts);
  });

  it('adds the unmatched equity point as a rollover, the starting cash and the reset on ALL', () => {
    const history = paperHistoryFixture(1_800_000_000);
    const rows = ledgerRows(history);
    const rollover = rows.filter((r) => r.kind === 'rollover');
    expect(rollover).toHaveLength(1);
    expect(rollover[0].balance).toBe(100000);
    expect(rollover[0].amount).toBeNull();
    const start = rows.find((r) => r.kind === 'start')!;
    expect(start.amount).toBe(100000);
    expect(start.ts).toBe(isoToTs('2026-09-18T16:12:40-04:00'));
    const reset = rows.find((r) => r.kind === 'reset')!;
    expect(reset.archive).toEqual({ file: 'practice-paper-2026-09-18T1612.json', realized: 192.85 });
    // Same timestamp: the starting cash lands above the reset it followed.
    expect(rows.indexOf(start)).toBeLessThan(rows.indexOf(reset));
  });

  it('leaves the starting cash and resets out of a bounded range that starts after them', () => {
    const history = paperHistoryFixture(1_800_000_000);
    history.range = '1D';
    history.range_start = 1_800_000_000 - 3 * 3600;
    const rows = ledgerRows(history);
    expect(rows.some((r) => r.kind === 'start')).toBe(false);
    expect(rows.some((r) => r.kind === 'reset')).toBe(false);
    expect(rows.filter((r) => r.kind === 'fill')).toHaveLength(6);
  });

  it('a fill without its equity point has no balance rather than a computed one', () => {
    const history = paperHistoryFixture(1_800_000_000);
    history.equity = [];
    const rows = ledgerRows(history).filter((r) => r.kind === 'fill');
    expect(rows.every((r) => r.balance === null)).toBe(true);
    expect(fillCashMovement(history.fills[0])).toBeCloseTo(-(500 * 5.1 + 2.5), 6);
  });
});
