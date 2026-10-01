/**
 * @vitest-environment jsdom
 *
 * The walk-away status says what it is: advisory, gating nothing (spec D, 2026-09-30). Every
 * sender passes skip_risk, so "Can trade / Halted" promised a gate that does not exist, and the
 * Journal's words still named the executor retired by ADR 025.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  JournalPanel,
  WALK_AWAY_LABEL,
  WALK_AWAY_TRIPPED,
  WALK_AWAY_WITHIN,
} from './JournalPanel';
import type { RiskStatus } from './types';

const state = vi.hoisted(() => ({ risk: null as RiskStatus | null }));

vi.mock('./useJournal', () => ({
  useJournal: () => ({ metrics: null, signals: [], trades: [], risk: state.risk, loading: false, error: null }),
}));

function risk(canTrade: boolean): RiskStatus {
  return {
    session_date: '2026-09-30', daily_realized_pnl: -120, peak_daily_pnl: 80, consecutive_losses: 3,
    consecutive_wins: 0, trades_today: 5, can_trade: canTrade,
    halt_reason: canTrade ? null : '3 losses in a row', position_size_shares: 100, daily_goal_dollars: 200,
  };
}

function renderPanel() {
  return render(
    <JournalPanel active selectedSymbol={null} onSelectSymbol={() => {}} onOpenTrading={() => {}} />,
  );
}

afterEach(() => {
  cleanup();
  state.risk = null;
});

describe('JournalPanel walk-away status', () => {
  it('labels the rules advisory and says they gate nothing', () => {
    state.risk = risk(false);
    const { container } = renderPanel();
    const status = screen.getByTestId('journal-walk-away-status');
    expect(status.textContent).toContain(WALK_AWAY_LABEL);
    expect(status.textContent).toContain(WALK_AWAY_TRIPPED);
    expect(status.getAttribute('title')).toMatch(/no order checks these rules/);
    expect(status.textContent).not.toMatch(/Halted|Can trade/);
    expect(container.innerHTML).not.toMatch(/executor/i);
  });

  it('says within limits when no rule tripped', () => {
    state.risk = risk(true);
    renderPanel();
    expect(screen.getByTestId('journal-walk-away-status').textContent).toContain(WALK_AWAY_WITHIN);
  });
});
