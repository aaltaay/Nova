/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { ActivityTrail } from './ActivityTrail';
import type { TrailItem } from './types';

const CLOSED: TrailItem = {
  id: 'trade:1',
  kind: 'closed',
  trade_id: 1,
  symbol: 'IVF',
  side: 'long',
  qty: 10,
  entry_price: 5,
  exit_price: 6.5,
  pnl: 12.75,
  commission: 2.25,
  pnl_basis: 'net',
  opened_ts: 1_700_000_000,
  closed_ts: 1_700_000_100,
  close_key: 'IVF|buy|flat',
  notes: 'Nova round trip buy -> flat; net of CommissionReport $2.25',
  events: [
    { kind: 'place', ts: 1_700_000_000, side: 'BUY', qty: 10, price: null },
    { kind: 'fill', ts: 1_700_000_010, side: 'BUY', qty: 10, price: 5 },
    { kind: 'flatten', ts: 1_700_000_080, side: 'SELL', qty: 10, price: null },
    { kind: 'fill', ts: 1_700_000_090, side: 'SELL', qty: 10, price: 6.5 },
    { kind: 'commission', ts: 1_700_000_090, commission: 1.25 },
    { kind: 'close', ts: 1_700_000_100, pnl: 12.75, commission: 2.25 },
  ],
};

describe('ActivityTrail', () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function mount(node: ReactNode) {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(node);
    });
  }

  it('shows the closed-cycle steps and stored net P/L', () => {
    mount(<ActivityTrail items={[CLOSED]} />);
    expect(container.querySelector('[data-testid="activity-trail"]')).toBeTruthy();
    expect(container.textContent).toContain('IVF');
    expect(container.textContent).toContain('$12.75');
    expect(container.textContent).toContain('$2.25');
    expect(container.textContent).toContain('Place -> Fill -> Flatten -> Fill -> Commission -> Close');
    expect(container.textContent).toContain('closed · net');
  });

  it('does not invent $0 commission on an open session row', () => {
    const openRow: TrailItem = {
      id: 'open:AAPL',
      kind: 'open',
      symbol: 'AAPL',
      pnl: null,
      commission: null,
      events: [{ kind: 'place', ts: 1_700_000_000, side: 'BUY', qty: 1 }],
    };
    mount(<ActivityTrail items={[openRow]} />);
    expect(container.textContent).toContain('AAPL');
    expect(container.textContent).toContain('open');
    const cells = Array.from(container.querySelectorAll('td')).map(node => node.textContent);
    expect(cells).toContain('--');
    expect(container.textContent).not.toContain('$0.00');
  });

  it('expands a cycle to the per-step table', () => {
    mount(<ActivityTrail items={[CLOSED]} />);
    const row = container.querySelector('[data-testid="activity-trail-row-trade:1"]');
    expect(row).toBeTruthy();
    act(() => {
      (row as HTMLTableRowElement).click();
    });
    expect(container.querySelector('[data-testid="activity-trail-detail-trade:1"]')).toBeTruthy();
    expect(container.textContent).toContain('close_key IVF|buy|flat');
    expect(container.textContent).toContain('Flatten');
  });
});