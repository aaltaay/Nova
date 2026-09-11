import { describe, expect, it } from 'vitest';
import { isSpendLocked, spendLockReason, spendStatusLabel } from './spendLock';

describe('isSpendLocked', () => {
  it('treats the armed statuses as unlocked', () => {
    expect(isSpendLocked('paper_armed')).toBe(false);
    expect(isSpendLocked('live_armed')).toBe(false);
  });

  it('treats every known locked status as locked', () => {
    expect(isSpendLocked('locked')).toBe(true);
    expect(isSpendLocked('locked_live_unconfirmed')).toBe(true);
    expect(isSpendLocked('locked_account_unconfirmed')).toBe(true);
  });

  it('fails closed for an unknown or missing status (D-038)', () => {
    expect(isSpendLocked(undefined)).toBe(true);
    expect(isSpendLocked('')).toBe(true);
    expect(isSpendLocked('some_future_backend_state')).toBe(true);
  });
});

describe('spendLockReason', () => {
  it('is null while armed, even with a stale backend reason', () => {
    expect(spendLockReason('paper_armed')).toBeNull();
    expect(spendLockReason('live_armed', 'stale reason')).toBeNull();
  });

  it('prefers the backend-authored reason', () => {
    expect(
      spendLockReason('locked_account_unconfirmed', 'live door but accounts are paper'),
    ).toBe('live door but accounts are paper');
  });

  it('falls back to a per-status reason', () => {
    expect(spendLockReason('locked')).toContain('enable IBKR orders');
    expect(spendLockReason('locked_live_unconfirmed')).toContain('live confirmation');
    expect(spendLockReason('locked_account_unconfirmed')).toContain('account class');
  });

  it('always has a reason for an unmapped locked status', () => {
    expect(spendLockReason('mystery')).toBeTruthy();
  });
});

describe('spendStatusLabel', () => {
  it('labels the three operator-visible cases', () => {
    expect(spendStatusLabel('paper_armed')).toBe('PAPER ORDERS ON');
    expect(spendStatusLabel('live_armed')).toBe('LIVE ORDERS ARMED');
    expect(spendStatusLabel('locked_account_unconfirmed')).toBe(
      'ORDERS LOCKED — no spends',
    );
  });
});
