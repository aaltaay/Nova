/**
 * @vitest-environment jsdom
 */
import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceProvider } from '../workspace/WorkspaceContext';
import { makeDetail } from '../modules/quoteFixtures';
import { StockViewQuoteCard } from './StockViewQuoteCard';
import { StockViewRail } from './StockViewRail';
import { StockViewDepthTape } from './StockViewDepthTape';
import { StockViewSymbolChip } from './StockViewSymbolChip';
import { StockViewPage } from '../pages/StockViewPage';
import { TickerTradeActionBar } from '../ibkr/TickerTradeActionBar';
import type { IbkrAccountSummary } from '../ibkr/types';
import {
  STOCK_VIEW_MODULE_DEPTH_TITLE,
  STOCK_VIEW_MODULE_L2_TITLE,
  STOCK_VIEW_MODULE_OPEN_TITLE,
  STOCK_VIEW_MODULE_QUOTE_TITLE,
  STOCK_VIEW_MODULE_TAPE_TITLE,
  STOCK_VIEW_SYMBOL_EDIT_TITLE,
} from '../constants';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: true,
    mode: 'paper',
    orders_enabled: false,
    spend_status: 'locked',
  }),
}));

vi.mock('../ibkr/useIbkrAccount', () => ({
  useIbkrAccount: () => ({
    summary: {
      connected: true,
      mode: 'paper',
      NetLiquidation: 100_000,
      BuyingPower: 50_000,
    } satisfies IbkrAccountSummary,
    positions: [],
    orders: [],
    refresh: vi.fn(),
  }),
}));

const tickerStreamState = {
  detailSymbol: null as string | null,
  selectedPassthrough: true,
};

vi.mock('../hooks/useTickerStream', () => ({
  useTickerStream: (symbol: string) => {
    const detailSym = tickerStreamState.selectedPassthrough
      ? symbol
      : (tickerStreamState.detailSymbol ?? 'STALE');
    return {
      detail: makeDetail({ symbol: detailSym }),
      loading: false,
      refreshing: false,
      fetchFailed: false,
    };
  },
}));

vi.mock('../components/ChartGrid', () => ({
  ChartGrid: ({ symbol }: { symbol: string }) => (
    <div data-testid="chart-grid" data-symbol={symbol}>
      charts
    </div>
  ),
}));

vi.mock('../modules/Level2Module', () => ({
  Level2Module: ({ symbol }: { symbol: string }) => (
    <div data-module="level2" data-symbol={symbol}>
      l2
    </div>
  ),
}));

vi.mock('../modules/TimeSalesModule', () => ({
  TimeSalesModule: ({ symbol, embedded }: { symbol: string; embedded?: boolean }) => (
    <div data-module="time-sales" data-symbol={symbol} data-embedded={embedded ? '1' : '0'}>
      {embedded ? <h3 className="sv-md-pane__title">{STOCK_VIEW_MODULE_TAPE_TITLE}</h3> : null}
      tape
    </div>
  ),
}));

vi.mock('../ibkr/TickerTradeAutomateControls', () => ({
  TickerTradeAutomateControls: () => <div data-testid="automate">Automate</div>,
}));

vi.mock('../strategy/useExecutor', () => ({
  useExecutor: () => ({
    status: null,
    actionError: null,
    setMode: vi.fn(),
    disarm: vi.fn(),
    killSwitch: vi.fn(),
    resetKillSwitch: vi.fn(),
  }),
}));

vi.mock('../strategy/useNovaOsDecideSymbol', () => ({
  useNovaOsDecideSymbol: () => ({
    decision: null,
    loading: false,
    error: null,
    errorStatus: null,
    updatedAt: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('../workspace', async () => {
  const actual = await vi.importActual<typeof import('../workspace')>('../workspace');
  return {
    ...actual,
    useWorkspace: () => ({
      ...actual.useWorkspace?.(),
      ibkrConnected: true,
      discoveryProvider: 'ibkr',
    }),
    useModuleVisibility: () => ({
      isVisible: () => true,
      setVisible: () => {},
      visibility: {},
    }),
  };
});

function wrap(ui: ReactNode) {
  return <WorkspaceProvider>{ui}</WorkspaceProvider>;
}

const summary: IbkrAccountSummary = {
  connected: true,
  mode: 'paper',
  NetLiquidation: 100_000,
  BuyingPower: 50_000,
};

describe('StockViewQuoteCard', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/api/config')) {
          return { ok: true, json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }) };
        }
        return { ok: false, json: async () => ({}) };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('renders module card title and dense stats without duplicate price', async () => {
    await act(async () => {
      root.render(wrap(<StockViewQuoteCard detail={makeDetail()} hidePrice />));
    });
    expect(container.querySelector('[data-module="stock-view-quote"]')).toBeTruthy();
    expect(container.textContent).toMatch(new RegExp(STOCK_VIEW_MODULE_QUOTE_TITLE, 'i'));
    expect(container.textContent).toMatch(/Float|Vol|Gap|RVol/);
    expect(container.querySelector('.sv-quote-card__price')).toBeNull();
    expect(container.querySelector('.sv-module-card')).toBeTruthy();
  });

  it('shows price block when hidePrice is false', async () => {
    await act(async () => {
      root.render(wrap(<StockViewQuoteCard detail={makeDetail()} hidePrice={false} />));
    });
    expect(container.querySelector('.sv-quote-card__symbol')?.textContent).toBe('AAPL');
    expect(container.querySelector('.sv-quote-card__last')?.textContent).toBe('190.50');
  });
});

describe('StockViewDepthTape', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('keeps L2 and T&S side-by-side in one module with no splitter between them', async () => {
    await act(async () => {
      root.render(
        wrap(<StockViewDepthTape selectedSymbol="AAPL" detailSymbol="AAPL" />),
      );
    });
    const stack = container.querySelector('[data-testid="stock-view-depth-stack"]');
    expect(stack).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-depth-side-by-side"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-l2-col"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-tape-col"]')).toBeTruthy();
    expect(container.querySelector('.depth-and-tape')).toBeTruthy();
    expect(container.querySelector('.resize-handle--horizontal')).toBeNull();
    // Outer combined title is gone — matched pane headers label each side.
    expect(stack!.querySelector('.sv-module-card__title')).toBeNull();
    expect(container.textContent).toMatch(new RegExp(STOCK_VIEW_MODULE_L2_TITLE, 'i'));
    expect(container.textContent).toMatch(new RegExp(STOCK_VIEW_MODULE_TAPE_TITLE, 'i'));
    expect(stack!.getAttribute('aria-label')).toMatch(new RegExp(STOCK_VIEW_MODULE_DEPTH_TITLE, 'i'));
  });
});

describe('StockViewRail order', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/api/config')) {
          return { ok: true, json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }) };
        }
        return { ok: false, json: async () => ({}) };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('composes quote → L2|T&S combined → horizontal drag → open ticket', async () => {
    await act(async () => {
      root.render(
        wrap(
          <StockViewRail
            symbol="AAPL"
            detail={makeDetail()}
            mode="paper"
            connected
            spendStatus="locked"
            position={null}
            summary={summary}
            referencePrice={190.5}
            onOrderPlaced={() => {}}
          />,
        ),
      );
    });
    const rail = container.querySelector('[data-testid="stock-view-rail"]');
    expect(rail).toBeTruthy();
    expect(rail!.querySelector('[data-module="stock-view-quote"]')).toBeTruthy();
    expect(rail!.querySelector('[data-testid="stock-view-trade-stack"]')).toBeTruthy();
    expect(rail!.querySelector('[data-testid="stock-view-depth-slot"]')).toBeTruthy();
    expect(rail!.querySelector('[data-testid="stock-view-depth-side-by-side"]')).toBeTruthy();
    expect(rail!.querySelector('[data-testid="stock-view-open-card"]')).toBeTruthy();
    expect(rail!.querySelector('[data-testid="stock-view-working-orders"]')).toBeNull();
    expect(rail!.querySelector('.manual-order-ticket')).toBeTruthy();
    expect(rail!.textContent).toMatch(/Unlock Trading/i);
    expect(rail!.textContent).toMatch(new RegExp(STOCK_VIEW_MODULE_OPEN_TITLE, 'i'));
    // Exactly one horizontal splitter — between depth and order, not between L2 and T&S
    const handles = rail!.querySelectorAll('.resize-handle--horizontal');
    expect(handles.length).toBe(1);
    const tradeHtml = rail!.querySelector('[data-testid="stock-view-trade-stack"]')!.innerHTML;
    expect(tradeHtml.indexOf('stock-view-depth-slot')).toBeLessThan(
      tradeHtml.indexOf('resize-handle--horizontal'),
    );
    expect(tradeHtml.indexOf('resize-handle--horizontal')).toBeLessThan(
      tradeHtml.indexOf('stock-view-open-card'),
    );
    // Three major modules: quote, combined depth, open (orders dock is page-level)
    expect(rail!.querySelectorAll('.sv-module-card').length).toBe(3);
  });
});

describe('TickerTradeActionBar rail', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('always mounts ManualOrderTicket and shows locked trading reason', async () => {
    await act(async () => {
      root.render(
        <TickerTradeActionBar
          symbol="MSFT"
          mode="paper"
          connected
          spendStatus="locked"
          position={null}
          summary={summary}
          referencePrice={100}
          variant="rail"
        />,
      );
    });
    expect(container.querySelector('.manual-order-ticket')).toBeTruthy();
    expect(container.querySelector('.ticker-trade-bar--rail')).toBeTruthy();
    expect(container.textContent).toMatch(/Orders locked|Unlock Trading/i);
    expect(container.querySelector('.ticker-trade-bar-automate')).toBeNull();
    expect(container.textContent).not.toMatch(/Net Liq/);
  });
});

describe('StockViewSymbolChip edit', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function setInputValue(input: HTMLInputElement, value: string) {
    const tracker = (
      input as unknown as { _valueTracker?: { setValue: (v: string) => void } }
    )._valueTracker;
    const prev = input.value;
    input.value = value;
    tracker?.setValue(prev);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function renderChip(onCommit = vi.fn()) {
    act(() => {
      root.render(
        <div className="stock-view-page">
          <StockViewSymbolChip
            symbol="AAPL"
            mainPrice={190.12}
            mainChangeAbs={1.5}
            mainChangePct={0.8}
            isPositive
            refreshing={false}
            onCommit={onCommit}
          />
        </div>,
      );
    });
    return onCommit;
  }

  function openEditor() {
    const chip = container.querySelector(
      '[data-testid="stock-view-symbol-chip"]',
    ) as HTMLElement;
    act(() => {
      chip.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    return container.querySelector(
      '[data-testid="stock-view-symbol-chip-edit"] input',
    ) as HTMLInputElement;
  }

  it('exposes double-click affordances and has no Look Up form', () => {
    renderChip();
    const chip = container.querySelector(
      '[data-testid="stock-view-symbol-chip"]',
    ) as HTMLElement;
    expect(chip).toBeTruthy();
    expect(chip.getAttribute('title')).toBe(STOCK_VIEW_SYMBOL_EDIT_TITLE);
    expect(container.textContent).not.toMatch(/Look Up/i);
    expect(container.querySelector('.sv-header__lookup')).toBeNull();
  });

  it('double-click enters edit; Enter commits uppercase symbol', () => {
    const onCommit = renderChip();
    const input = openEditor();
    expect(input).toBeTruthy();
    act(() => {
      setInputValue(input, '  tsla ');
      input.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      );
    });
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith('TSLA');
  });

  it('Escape cancels without committing', () => {
    const onCommit = renderChip();
    const input = openEditor();
    act(() => {
      setInputValue(input, 'MSFT');
      input.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
      );
    });
    expect(onCommit).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="stock-view-symbol-chip"]')).toBeTruthy();
    expect(container.textContent).toMatch(/AAPL/);
  });

  it('rejects empty commit', () => {
    const onCommit = renderChip();
    const input = openEditor();
    act(() => {
      setInputValue(input, '   ');
      input.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      );
    });
    expect(onCommit).not.toHaveBeenCalled();
  });
});

describe('StockViewPage symbol gate', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/api/config')) {
          return { ok: true, json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }) };
        }
        return { ok: false, json: async () => ({}) };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('renders terminal chrome, charts, and rail for matching symbol', async () => {
    tickerStreamState.selectedPassthrough = true;
    await act(async () => {
      root.render(
        wrap(
          <StockViewPage
            symbol="AAPL"
            onBack={() => {}}
            onSelectSymbol={() => {}}
          />,
        ),
      );
    });
    expect(container.querySelector('.stock-view-page')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-header"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-symbol-chip"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sv-account-mode-capsule"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sv-operator-mode-capsule"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sv-trading-lock"]')).toBeNull();
    expect(container.textContent).toMatch(/Net Liq/);
    expect(container.textContent).toMatch(/BP/);
    expect(container.textContent).toMatch(/Normal/);
    expect(container.textContent).toMatch(/Paper/);
    expect(container.textContent).not.toMatch(/Look Up/i);
    expect(container.textContent).not.toMatch(/Hide charts/i);
    expect(container.textContent).not.toMatch(/Stop Automation/i);
    expect(container.textContent).not.toMatch(/✕ Close|← Back/);
    expect(container.querySelector('.ticker-trade-bar-automate')).toBeNull();
    expect(container.querySelector('[data-testid="chart-grid"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-rail"]')).toBeTruthy();
    expect(container.querySelector('.manual-order-ticket')).toBeTruthy();
    expect(container.querySelector('[data-module="news"]')).toBeNull();
    expect(container.querySelector('[data-module="data-sources"]')).toBeNull();
  });

  it('keeps Manual and Fully Automated disabled; Normal selected', async () => {
    tickerStreamState.selectedPassthrough = true;
    await act(async () => {
      root.render(
        wrap(
          <StockViewPage
            symbol="AAPL"
            onBack={() => {}}
            onSelectSymbol={() => {}}
          />,
        ),
      );
    });
    const capsule = container.querySelector('[data-testid="sv-operator-mode-capsule"]');
    expect(capsule).toBeTruthy();
    const segs = capsule!.querySelectorAll('.sv-capsule__seg');
    expect(segs).toHaveLength(3);
    expect((segs[0] as HTMLButtonElement).disabled).toBe(true);
    expect((segs[0] as HTMLButtonElement).textContent).toMatch(/Manual/);
    expect((segs[1] as HTMLButtonElement).disabled).toBe(false);
    expect((segs[1] as HTMLButtonElement).classList.contains('is-selected')).toBe(true);
    expect((segs[1] as HTMLButtonElement).textContent).toMatch(/Normal/);
    expect((segs[2] as HTMLButtonElement).disabled).toBe(true);
    expect((segs[2] as HTMLButtonElement).textContent).toMatch(/Fully Automated/);
  });

  it('hides live rail/charts when detail.symbol mismatches selected symbol', async () => {
    tickerStreamState.selectedPassthrough = false;
    tickerStreamState.detailSymbol = 'NXTC';
    await act(async () => {
      root.render(
        wrap(
          <StockViewPage
            symbol="MVO"
            onBack={() => {}}
            onSelectSymbol={() => {}}
          />,
        ),
      );
    });
    expect(container.querySelector('[data-testid="stock-view-rail"]')).toBeNull();
    expect(container.querySelector('[data-testid="chart-grid"]')).toBeNull();
    expect(container.querySelector('.manual-order-ticket')).toBeNull();
    // Dock stays mounted — Positions/Orders do not depend on ticker detail.
    expect(
      container.querySelector('[data-testid="stock-view-open-orders-dock"]'),
    ).toBeTruthy();
    expect(container.textContent).toMatch(/Loading MVO/i);
  });
});
