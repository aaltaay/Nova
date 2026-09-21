/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';

vi.mock('../practice/PracticeAccountStrip', () => ({
  PracticeAccountStrip: ({ venue }: { venue: string | null }) =>
    venue === 'paper' || venue === 'sim' ? <div data-testid="practice-strip">{venue}</div> : null,
}));

afterEach(cleanup);

function mount(venue: 'live' | 'paper' | 'sim' | 'disconnected' | undefined) {
  render(
    <GlobalBarAccountCluster
      accountChrome="offline"
      accountError={null}
      summary={null}
      orders={[]}
      workingCount={0}
      openMenu={null}
      setOpenMenu={() => {}}
      accountCardId="card"
      workingMenuId="menu"
      closedOrders={[]}
      traderActive={false}
      closeTraderView={() => {}}
      refresh={() => {}}
      venue={venue}
    />,
  );
}

describe('GlobalBarAccountCluster -- practice strip (ADR 020)', () => {
  it('hands the desk venue to the practice strip', () => {
    mount('paper');
    expect(screen.getByTestId('practice-strip').textContent).toBe('paper');
    cleanup();
    mount('sim');
    expect(screen.getByTestId('practice-strip').textContent).toBe('sim');
  });

  it('shows no practice strip on Live, while disconnected, or when no venue is given', () => {
    for (const venue of ['live', 'disconnected', undefined] as const) {
      mount(venue);
      expect(screen.queryByTestId('practice-strip')).toBeNull();
      cleanup();
    }
  });
});
