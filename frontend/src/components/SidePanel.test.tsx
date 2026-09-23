/**
 * @vitest-environment jsdom
 *
 * The Scanner side panel's look-up (QA V36, operator decision 2026-09-22,
 * option a): it loads the Quote Panel in place, the global bar's search opens
 * the Trader, and the two must not read as the same door.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GLOBAL_BAR_SEARCH_ARIA } from '../constantGroups/global_bar';
import {
  QUOTE_PANEL_COLLAPSE,
  QUOTE_PANEL_EXPAND,
  QUOTE_PANEL_LOOKUP_ARIA,
  QUOTE_PANEL_LOOKUP_PLACEHOLDER,
} from '../constantGroups/scanner_board';
import { SidePanel } from './SidePanel';

const { workspace } = vi.hoisted(() => ({
  workspace: {
    selectedSymbol: null as string | null,
    setSelectedSymbol: vi.fn(),
    openStockView: vi.fn(),
  },
}));

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));
const streamed = vi.hoisted(() => [] as Array<string | null>);
vi.mock('../hooks/useTickerStream', () => ({
  useTickerStream: (symbol: string | null) => (streamed.push(symbol), {
    detail: null,
    loading: false,
    refreshing: false,
    fetchFailed: false,
    stale: false,
    disconnectedSince: null,
  }),
}));
vi.mock('./TickerDetailContent', () => ({
  TickerDetailContent: () => null,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  streamed.length = 0;
  workspace.selectedSymbol = null;
});

describe('SidePanel look-up (QA V36)', () => {
  it('names itself as the Quote Panel door, not the header search', () => {
    render(<SidePanel />);

    expect(screen.getByRole('button', { name: 'Quote panel: look up' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Look Up' })).toBeNull();

    const input = screen.getByRole('textbox', { name: QUOTE_PANEL_LOOKUP_ARIA });
    expect(QUOTE_PANEL_LOOKUP_ARIA).toMatch(/quote panel on this page/i);
    expect(screen.queryByRole('textbox', { name: GLOBAL_BAR_SEARCH_ARIA })).toBeNull();
    expect(input.getAttribute('placeholder')).toBe(QUOTE_PANEL_LOOKUP_PLACEHOLDER);
  });

  it('still loads the symbol in place and never opens the Trader', () => {
    render(<SidePanel />);

    fireEvent.change(screen.getByRole('textbox', { name: QUOTE_PANEL_LOOKUP_ARIA }), {
      target: { value: ' aapl ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Quote panel: look up' }));

    expect(workspace.setSelectedSymbol).toHaveBeenCalledWith('AAPL');
    expect(workspace.openStockView).not.toHaveBeenCalled();
  });
});

describe('SidePanel collapse (operator ask, 2026-09-23)', () => {
  it('folds to a strip on the right that names the symbol, and unfolds from it', () => {
    workspace.selectedSymbol = 'WHLR';
    const onToggle = vi.fn();
    const { rerender } = render(<SidePanel collapsed={false} onToggleCollapsed={onToggle} />);
    expect(screen.getByTestId('quote-panel').getAttribute('data-collapsed')).toBe('0');
    fireEvent.click(screen.getByRole('button', { name: QUOTE_PANEL_COLLAPSE }));
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(<SidePanel collapsed onToggleCollapsed={onToggle} />);
    expect(screen.getByTestId('quote-panel').getAttribute('data-collapsed')).toBe('1');
    expect(screen.getByTestId('quote-panel-expand').textContent).toBe('Quote Panel · WHLR');
    expect(screen.queryByRole('textbox', { name: QUOTE_PANEL_LOOKUP_ARIA })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: QUOTE_PANEL_EXPAND }));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('streams nothing while folded', () => {
    workspace.selectedSymbol = 'WHLR';
    render(<SidePanel collapsed onToggleCollapsed={() => {}} />);
    expect(streamed.every(sym => sym === null)).toBe(true);
    cleanup();
    render(<SidePanel collapsed={false} onToggleCollapsed={() => {}} />);
    expect(streamed.at(-1)).toBe('WHLR');
  });

  it('has no collapse control where the host gives it no toggle', () => {
    render(<SidePanel />);
    expect(screen.queryByTestId('quote-panel-collapse')).toBeNull();
  });
});
