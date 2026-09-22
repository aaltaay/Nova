/**
 * @vitest-environment jsdom
 *
 * The header account cluster after the QA sweep of 2026-09-22: a click after
 * the hover that opened a card keeps it open (V15); the status's own venue
 * wins over a Gateway-label mode (C26); the sample desk shows only its sample
 * summary and never polls a practice account (V4); the Day P&L tooltip names
 * its day start in ET (C61).
 */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrAccountSummary } from '../ibkr/types';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import { PAPER_ACCOUNT as PAPER } from '../practice/practiceFixtures';
import type { PracticeAccount } from '../practice/practiceTypes';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';

const { status, practice, practiceVenues } = vi.hoisted(() => ({
  status: { current: {} as IbkrClientStatus },
  practice: { current: { data: null as PracticeAccount | null, error: null as string | null } },
  practiceVenues: [] as Array<string | null | undefined>,
}));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => status.current }));
vi.mock('../practice/practiceAccountResource', () => ({
  usePracticeAccount: (venue: string | null | undefined) => {
    practiceVenues.push(venue);
    return practice.current;
  },
}));

const SUMMARY: IbkrAccountSummary = {
  connected: true, mode: 'paper', AccountType: 'INDIVIDUAL', account_class: 'margin',
  NetLiquidation: 3559.55, TotalCashValue: 3558.53, BuyingPower: 7117.06, UnrealizedPnL: -0.17, RealizedPnL: 12.5,
};

function mount(venue: string) {
  render(
    <GlobalBarAccountCluster
      accountChrome="ready"
      accountError={null}
      summary={SUMMARY}
      orders={[]}
      closedOrders={[]}
      traderActive={false}
      closeTraderView={() => {}}
      refresh={() => {}}
      venue={venue as never}
    />,
  );
}

beforeEach(() => {
  practiceVenues.length = 0;
  practice.current = { data: { ...PAPER, day_started_et: '2026-09-21T04:00:00-04:00' }, error: null };
  status.current = {
    enabled: true, connected: true, mode: 'paper', venue: 'paper', account_id: 'NOVA-PAPER',
    clientReady: true, stale: false, staleSince: null,
  } as IbkrClientStatus;
});

afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
});

describe('GlobalBarAccountCluster (QA batch)', () => {
  it('a click after the hover that opened the Day card keeps it open (V15)', () => {
    mount('paper');
    const trigger = screen.getByTestId('global-bar-account-trigger');
    fireEvent.mouseEnter(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    act(() => {
      trigger.click();
    });
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByTestId('global-bar-day-card')).toBeTruthy();
    act(() => {
      trigger.click();
    });
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('the Day P&L tooltip names the day start in ET, not the raw ISO (C61)', () => {
    mount('paper');
    const title = screen.getByTestId('global-bar-account-trigger').getAttribute('title') ?? '';
    expect(title).toContain('Mon, Sep 21, 04:00 ET');
    expect(title).not.toContain('2026-09-21T04:00:00');
  });

  it('Live on the by-hand paper Gateway shows the IBKR account, not NOVA-PAPER (C26)', () => {
    status.current = { ...status.current, mode: 'paper', venue: 'live', account_id: 'DU1234567', account_ids: ['DU1234567'] };
    mount('paper');
    expect(screen.getByTestId('global-bar-account').getAttribute('data-venue')).toBe('live');
    expect(screen.getByTestId('global-bar-account').getAttribute('data-source')).toBe('ibkr');
    expect(screen.getByTestId('global-bar-account-pill').getAttribute('data-account-id')).toBe('DU1234567');
    expect(practiceVenues.every((venue) => venue === 'live')).toBe(true);
  });

  it('the sample desk shows its sample summary and polls no practice account (V4)', () => {
    window.history.replaceState({}, '', '/?view=sample');
    mount('paper');
    expect(screen.getByTestId('global-bar-account').getAttribute('data-source')).toBe('ibkr');
    expect(screen.getByTestId('global-bar-tav-trigger').textContent).toContain('$3,559.55');
    expect(practiceVenues.every((venue) => venue == null)).toBe(true);
  });
});
