/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { WhyMovingRead } from '../types/whyMoving';
import { CatalystExplain, ladderParts } from './CatalystExplain';

const MNDR: WhyMovingRead = {
  schema_version: 1,
  symbol: 'MNDR',
  generated_at: Date.parse('2026-10-12T20:49:00-04:00') / 1000,
  rules_version: 'move-rules-v6-2026-10-13',
  replay: false,
  likely: {
    kind: 'low_float_momentum',
    label: 'Low-float momentum -- no company news; borrow is tight',
    detail: 'Volume vs float: Float traded 144x; Borrow (IBKR): Nothing to lend',
    confidence: 'likely',
    steps: [
      { kind: 'move', name: 'A real move', fits: true, why: '+204.7% today' },
      { kind: 'news_pending', name: 'Halted for news', fits: false, why: 'No news halt open (T1 / T12)' },
      { kind: 'news', name: 'Company news', fits: false, why: 'Only movers lists and market wraps' },
      { kind: 'short_squeeze', name: 'Short squeeze', fits: false,
        why: 'Shorts 10% of float · 0.3 days to cover (Yahoo ratio) -- heavy is 20% of the float short, or 3+ days to cover with 10%+ short' },
      { kind: 'routine_news', name: 'Routine item', fits: false, why: 'Not a routine-only item' },
      { kind: 'split_squeeze', name: 'Split squeeze', fits: false, why: 'Reverse split: 1-for-6, 106 days ago -- needs one in the last 10 days' },
      { kind: 'low_float_momentum', name: 'Low-float momentum', fits: true, why: 'Up +204.7%; Float 398K? shares -- low float; Float traded 144x' },
      { kind: 'thin_trading', name: 'Thin trading', fits: false, why: 'RVOL 242x -- not below its usual volume' },
      { kind: 'unexplained', name: 'Unexplained', fits: false, why: 'A cause above fits' },
    ],
  },
  checks: [
    { id: 'borrow', label: 'Borrow (IBKR)', state: 'yes', value: 'Nothing to lend', detail: null,
      source: 'IBKR short-stock availability (every 15 min)', as_of: null },
  ],
  facts: {
    board: 'gappers', priced_by: 'board_row', price: 2.59, change_pct: 2.0471,
    last_trade: { price: 2.45, change_pct: 1.8824, ts: Date.parse('2026-10-12T20:52:00-04:00') / 1000 },
    catalyst: null,
  },
};

describe('CatalystExplain', () => {
  afterEach(cleanup);

  it('shows the rungs up to the call, never the ones after that do not fit', () => {
    const { shown, also } = ladderParts(MNDR.likely.steps ?? []);
    expect(shown.map(s => s.kind).at(-1)).toBe('low_float_momentum');
    expect(shown.map(s => s.kind)).not.toContain('thin_trading');
    expect(also).toEqual([]);
  });

  it('says the call, the price it was read at, why not a squeeze, and every fact with its source', () => {
    render(<CatalystExplain symbol="MNDR" read={MNDR} />);
    expect(screen.getByText('Low-float momentum -- no company news; borrow is tight')).toBeTruthy();
    const at = screen.getByTestId('catalyst-read-at').textContent ?? '';
    expect(at).toContain('MNDR read at $2.59 (+204.71%)');
    expect(at).toContain("this board row's price, as the board shows it (Gappers)");
    expect(at).toContain('Last trade $2.45 (+188.24%) at Oct 12 20:52 ET');
    const ladder = within(screen.getByTestId('catalyst-ladder'));
    expect(ladder.getByText(/heavy is 20% of the float short/)).toBeTruthy();
    expect(screen.getByText('IBKR short-stock availability (every 15 min)')).toBeTruthy();
    expect(document.querySelector('.cx-step--chosen')?.getAttribute('data-step')).toBe('low_float_momentum');
  });

  it('a read not in yet says so', () => {
    render(<CatalystExplain symbol="MNDR" read={null} loading />);
    expect(screen.getByText('Reading the move ...')).toBeTruthy();
  });
});
