/**
 * @vitest-environment jsdom
 *
 * The desk venue (ADR 020, QA C26), the Account module sections (V23) and the
 * practice reset copy (C43).
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { PRACTICE_STARTING_CASH_PLACEHOLDER, practiceResetConfirmMessage } from '../constantGroups/practice';
import {
  deskVenueOf,
  explicitVenueOf,
  isPracticeDeskVenue,
  practiceLedgerReachable,
  resolveDeskVenue,
} from './deskVenue';
import { buildTradingPrerequisites } from './tradingPrerequisites';
import { TradingSectionNav } from './TradingSectionNav';

afterEach(cleanup);

describe('desk venue (C26)', () => {
  it('the status venue wins over a Gateway-label mode', () => {
    expect(deskVenueOf({ venue: 'live', mode: 'paper' })).toBe('live');
    expect(resolveDeskVenue({ venue: 'live', mode: 'paper' }, 'paper')).toBe('live');
    expect(explicitVenueOf({ venue: 'sim' })).toBe('sim');
  });

  it('falls back to the mode only when no venue is stated', () => {
    expect(deskVenueOf({ mode: 'sim' })).toBe('sim');
    expect(deskVenueOf({ mode: 'disconnected' })).toBeNull();
    expect(explicitVenueOf({})).toBeNull();
    expect(resolveDeskVenue({ mode: 'paper' }, 'live')).toBe('live');
  });

  it('the practice ledger answers on Paper and Sim while the status is fresh (C68)', () => {
    expect(practiceLedgerReachable({ venue: 'paper', mode: 'paper' })).toBe(true);
    expect(practiceLedgerReachable({ venue: 'paper', mode: 'paper', stale: true })).toBe(false);
    expect(practiceLedgerReachable({ venue: 'live', mode: 'live' })).toBe(false);
    expect(isPracticeDeskVenue('paper')).toBe(true);
    expect(isPracticeDeskVenue('live')).toBe(false);
  });

  it('the prerequisites panel keeps the IBKR completed-orders notice off practice orders (C68)', () => {
    const input = {
      health: { status: 'connected', latency_ms: 0 },
      ibkrEnabled: true,
      ibkrConnected: true,
      completedOrdersUnansweredSince: 1_789_808_049,
    };
    const ids = (practiceOrders: boolean) =>
      buildTradingPrerequisites({ ...input, practiceOrders }).warnings.map((w) => w.id);
    expect(ids(false)).toContain('completed_orders');
    expect(ids(true)).not.toContain('completed_orders');
  });
});

describe('Account module sections (V23)', () => {
  it('a host can leave Overview -- the ticket and book -- out', () => {
    render(<TradingSectionNav section="reports" onChange={() => {}} sections={['reports', 'activity', 'latency']} />);
    expect(screen.queryByTestId('account-section-overview')).toBeNull();
    expect(screen.getByTestId('account-section-reports')).toBeTruthy();
  });
});

describe('practice reset copy (C43)', () => {
  it('says a blank amount resets to $100,000, never "unchanged"', () => {
    expect(practiceResetConfirmMessage('paper', null)).toContain('Starting cash resets to $100,000.');
    expect(practiceResetConfirmMessage('paper', null)).not.toMatch(/unchanged/);
    expect(practiceResetConfirmMessage('sim', '$50,000.00')).toContain('Starting cash will be $50,000.00.');
    expect(PRACTICE_STARTING_CASH_PLACEHOLDER).toMatch(/\$100,000/);
  });
});
