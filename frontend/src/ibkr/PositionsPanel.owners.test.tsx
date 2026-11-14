/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OWNER_OTHERS_UNREAD, ownerHoldSentence, ownerYoursToClose } from '../constantGroups/owners';
import type { DeskPosition } from './deskPositions';
import { PositionsPanel } from './PositionsPanel';

const row = (symbol: string, qty: number, extra: Partial<DeskPosition> = {}): DeskPosition => ({
  symbol, qty, market_price: 124.89, market_value: qty * 124.89, avg_cost: 125.9, unrealized_pnl: 19.19, realized_pnl: null,
  ...extra,
});
const claude = (symbol: string, qty: number) => row(symbol, qty, { owner: 'claude', bot: null });

function renderPanel(positions: DeskPosition[], props: { othersStale?: boolean } = {}) {
  render(
    <PositionsPanel
      summary={null}
      positions={positions}
      orders={[]}
      selectedSymbol={null}
      onSelectSymbol={vi.fn()}
      onOpenTrading={vi.fn()}
      othersStale={props.othersStale}
      mode="paper"
      connected
      compact
    />,
  );
}

const headers = () => [...screen.getByTestId('positions-table').querySelectorAll('th')]
  .map((th) => th.textContent?.replace('↕', ''));
const rowOf = (text: string) => screen.getByText(text).closest('tr') as HTMLElement;

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('PositionsPanel with every book (ADR 072)', () => {
  it("lists another trader's row beside yours and says whose each is", () => {
    renderPanel([row('INTC', 100, { owner: 'you', bot: null }), claude('ORCL', -19)]);
    expect(headers().slice(0, 3)).toEqual(['Symbol', 'Whose', 'Side']);
    expect(screen.getByTestId('positions-table').className).toContain('ibkr-table--whose');
    expect(within(rowOf('INTC')).getByTestId('account-whose').textContent).toBe('You');
    expect(within(rowOf('ORCL')).getByTestId('account-whose').textContent).toBe('Claude');
  });

  it("gives another trader's row no Close at all, and says why; your row keeps yours", () => {
    renderPanel([row('INTC', 100, { owner: 'you', bot: null }), claude('ORCL', -19)]);
    expect(within(rowOf('INTC')).queryByTestId('close-position-btn')).not.toBeNull();
    expect(within(rowOf('ORCL')).queryByTestId('close-position-btn')).toBeNull();
    expect(within(rowOf('ORCL')).queryByRole('button')).toBeNull();
    expect(within(rowOf('ORCL')).getByTestId('positions-others-no-close').getAttribute('title'))
      .toBe(ownerHoldSentence('claude', -19).trim());
  });

  it('marks the shares handed to you on your row with whose they were, dashed', () => {
    renderPanel([row('XLAB', 200, { owner: 'you', bot: null, handed_qty: 200, handed_from: 'brain' })]);
    const chips = within(rowOf('XLAB')).getAllByTestId('account-whose');
    // Every share there was handed: no You chip beside it. Your Close sells them.
    expect(chips.map((c) => [c.textContent, c.getAttribute('data-owner')])).toEqual([[ownerYoursToClose('brain'), 'brain']]);
    expect(chips[0].className).toContain('is-handed');
    expect(within(rowOf('XLAB')).queryByTestId('close-position-btn')).not.toBeNull();
  });

  it('keeps the You chip beside the handed one while some shares are your own', () => {
    renderPanel([row('XLAB', 300, { owner: 'you', bot: null, handed_qty: 200, handed_from: 'claude' })]);
    const chips = within(rowOf('XLAB')).getAllByTestId('account-whose');
    expect(chips.map((c) => c.getAttribute('data-owner'))).toEqual(['you', 'claude']);
    expect(chips[0].textContent).toBe('You');
  });

  it("keeps today's table where there is one book", () => {
    renderPanel([row('INTC', 100)]);
    expect(headers()).not.toContain('Whose');
    expect(screen.getByTestId('positions-table').className).not.toContain('ibkr-table--whose');
    expect(screen.queryByTestId('account-whose')).toBeNull();
  });

  it("never says nothing is held while the other traders' shares cannot be read, and your Close stays", () => {
    renderPanel([], { othersStale: true });
    expect(screen.getByTestId('positions-others-unread').textContent).toBe(OWNER_OTHERS_UNREAD);
    expect(screen.queryByTestId('positions-empty')).toBeNull();
    cleanup();
    const mine = [row('INTC', 100, { owner: 'you', bot: null })];
    const why = () => screen.getByTestId('close-position-btn').getAttribute('data-why');
    renderPanel(mine);
    const read = why();
    cleanup();
    renderPanel(mine, { othersStale: true });
    expect(why()).toBe(read);
  });
});
