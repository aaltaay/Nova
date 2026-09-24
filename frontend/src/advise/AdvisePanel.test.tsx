/**
 * @vitest-environment jsdom
 */
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdvisePanel } from './AdvisePanel';
import { AdviseProvider, useAdvise } from './AdviseContext';
import * as api from './adviseApi';
import * as ticket from './ticketFromStance';
import * as placeOrder from '../ibkr/placeOrder';

const openStockView = vi.fn();

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    selectedSymbol: 'AAPL',
    activeTraderSymbol: null,
    openStockView,
  }),
}));

const COMPLETE = {
  id: 7,
  symbol: 'AAPL',
  session_date: '2026-09-15',
  created_ts: 1_000,
  finished_ts: 1_100,
  model: 'sonnet',
  graph_version: 1,
  depth: 2,
  status: 'complete' as const,
  fail_reason: null,
  transcript: [{ type: 'message', agent: 'bull', content: 'long case' }],
  result: {
    stance: 'LONG' as const,
    reasons: ['gap'],
    risks: ['fade'],
    ticket: {
      symbol: 'AAPL',
      side: 'BUY' as const,
      order_type: 'MKT' as const,
      quantity_value: '100',
      limit_price: '',
      places: false as const,
    },
  },
  from_book: true,
  stale: false,
  stale_nudge: null,
  disclaimer: 'Advisory only',
  places: false as const,
  prompt_tokens: 80000,
  completion_tokens: 12000,
  actual_usd: 0.31,
};

function OpenOnMount() {
  const { openAdvise, open } = useAdvise();
  useEffect(() => {
    openAdvise();
  }, [openAdvise]);
  return open ? <AdvisePanel /> : null;
}

describe('AdvisePanel', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    openStockView.mockClear();
    vi.spyOn(api, 'fetchAdviseLatest').mockResolvedValue(COMPLETE);
    vi.spyOn(api, 'fetchAdviseHistory').mockResolvedValue([COMPLETE]);
    vi.spyOn(api, 'fetchAdviseEstimate').mockResolvedValue({
      symbol: 'AAPL',
      depth: 2,
      model: 'sonnet',
      model_label: 'Claude Sonnet',
      llm_calls: 14,
      est_usd: 0.5,
      est_minutes: 4,
      summary: '~$0.50 and ~4 min for 2 debate round(s)',
      disclaimer: 'Advisory only',
      note: 'Rough only',
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  it('shows book transcript, card, and ticket/chart without placing', async () => {
    const stage = vi.spyOn(ticket, 'stageAdviseTicket');
    await act(async () => {
      root.render(
        <AdviseProvider>
          <OpenOnMount />
        </AdviseProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="advise-overlay"]')).toBeTruthy();
    expect(container.textContent).toMatch(/long case/);
    expect(container.textContent).toMatch(/LONG/);
    expect(container.textContent).toMatch(/not auto-trading/);
    // A finished run: Run is open, and Cancel says why it is locked (ux/whyTip.ts).
    expect(container.querySelector('[data-testid="advise-run"]')?.hasAttribute('data-why')).toBe(false);
    expect(container.querySelector('[data-testid="advise-cancel"]')?.getAttribute('data-why'))
      .toBe('No run is queued or running -- nothing to cancel');
    await act(async () => {
      (container.querySelector('[data-testid="advise-jump-chart"]') as HTMLButtonElement).click();
    });
    expect(openStockView).toHaveBeenCalledWith('AAPL');
    await act(async () => {
      (container.querySelector('[data-testid="advise-open-ticket"]') as HTMLButtonElement).click();
    });
    expect(openStockView).toHaveBeenCalledWith('AAPL');
    await act(async () => {
      await new Promise((r) => setTimeout(r, 90));
    });
    expect(stage).toHaveBeenCalled();
    expect(container.querySelector('[data-testid="advise-estimate-headline"]')?.textContent)
      .toBe('Estimate: ~$0.50 · ~4 min');
    expect(container.querySelector('[data-testid="advise-actual"]')?.textContent)
      .toBe('Actual: $0.31');
    const history = container.querySelector('[data-testid="advise-history"]') as HTMLSelectElement;
    expect(history.querySelector('option[value="7"]')?.textContent).toMatch(/complete · \$0\.31/);
  });

  it('shows stale nudge, fail reason, Retry, and never places', async () => {
    const place = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const staleFail = {
      ...COMPLETE,
      status: 'failed' as const,
      fail_reason: 'OpenRouter HTTP 401',
      stale: true,
      stale_nudge: 'This run is over ~2 hours old. Refresh?',
      result: { ...COMPLETE.result, ticket: null },
    };
    vi.spyOn(api, 'fetchAdviseLatest').mockResolvedValue(staleFail);
    vi.spyOn(api, 'fetchAdviseHistory').mockResolvedValue([staleFail]);
    const retry = vi.spyOn(api, 'postAdviseRetry').mockResolvedValue({
      ...staleFail,
      id: 8,
      status: 'queued',
      fail_reason: null,
    });
    await act(async () => {
      root.render(
        <AdviseProvider>
          <OpenOnMount />
        </AdviseProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="advise-stale"]')?.textContent)
      .toMatch(/2 hours/);
    expect(container.querySelector('[data-testid="advise-fail"]')?.textContent)
      .toMatch(/401/);
    expect(container.querySelector('[data-testid="advise-actual"]')?.textContent)
      .toBe('Actual: $0.31');
    const history = container.querySelector('[data-testid="advise-history"]') as HTMLSelectElement;
    expect(history.value).toBe('7');
    expect(history.querySelector('option[value="7"]')?.textContent).toMatch(/failed · \$0\.31/);
    const retryBtn = container.querySelector('[data-testid="advise-retry"]') as HTMLButtonElement;
    expect(retryBtn).toBeTruthy();
    await act(async () => {
      retryBtn.click();
    });
    expect(retry).toHaveBeenCalledWith(7);
    expect(place).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="advise-open-ticket"]')).toBeNull();
    // The retried run is queued: Run says why it waits, Cancel opens.
    const runBtn = container.querySelector('[data-testid="advise-run"]') as HTMLButtonElement;
    expect(runBtn.disabled).toBe(true);
    expect(runBtn.getAttribute('data-why')).toBe('A run is already going -- wait for it, or Cancel it');
    expect(container.querySelector('[data-testid="advise-cancel"]')?.hasAttribute('data-why')).toBe(false);
  });

  it('closes on Escape like Settings (QA V29)', async () => {
    await act(async () => {
      root.render(
        <AdviseProvider>
          <OpenOnMount />
        </AdviseProvider>,
      );
    });
    expect(container.querySelector('[data-testid="advise-overlay"]')).toBeTruthy();
    const underneath = vi.fn();
    window.addEventListener('keydown', underneath);
    await act(async () => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    window.removeEventListener('keydown', underneath);
    expect(container.querySelector('[data-testid="advise-overlay"]')).toBeNull();
    // The dialog answers; a desk hotkey underneath does not also see the key.
    expect(underneath).not.toHaveBeenCalled();
  });
});
