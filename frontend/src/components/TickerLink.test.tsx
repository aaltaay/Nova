/**
 * @vitest-environment jsdom
 *
 * Every ticker is a shortcut to the Trader through one door (operator ask, 2026-10-15).
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import { TickerLink } from './TickerLink';

const workspace = vi.hoisted(() => ({ value: null as null | { openStockView: ReturnType<typeof vi.fn> } }));

vi.mock('../workspace', () => ({
  useWorkspace: () => {
    if (!workspace.value) throw new Error('useWorkspace must be used within WorkspaceProvider');
    return workspace.value;
  },
}));

afterEach(() => {
  cleanup();
  workspace.value = null;
});

describe('TickerLink', () => {
  it('opens the Trader through the workspace, and the row under it does not take the click', () => {
    const openStockView = vi.fn();
    workspace.value = { openStockView };
    const rowClick = vi.fn();
    render(<div onClick={rowClick}><TickerLink symbol="weto" /></div>);
    const link = screen.getByRole('button', { name: 'weto' });
    expect(link.classList.contains('symbol-btn')).toBe(true);
    expect(link.getAttribute('data-tip')).toBe(TICKER_OPEN_TRADER_TITLE);
    fireEvent.click(link);
    expect(openStockView).toHaveBeenCalledWith('WETO');
    expect(rowClick).not.toHaveBeenCalled();
  });

  it('passes the list it was picked from and a pin', () => {
    const openStockView = vi.fn();
    workspace.value = { openStockView };
    render(<TickerLink symbol="ABCD" from="gappers" pin />);
    fireEvent.click(screen.getByRole('button', { name: 'ABCD' }));
    expect(openStockView).toHaveBeenCalledWith('ABCD', { from: 'gappers', pin: true });
  });

  it('runs a caller\'s own open instead, with the same button', () => {
    const openStockView = vi.fn();
    workspace.value = { openStockView };
    const onOpen = vi.fn();
    render(<TickerLink symbol="EFGH" look="own" className="mine" onOpen={onOpen} />);
    const link = screen.getByRole('button', { name: 'EFGH' });
    expect(link.className).toBe('ticker-link mine');
    fireEvent.click(link);
    expect(onOpen).toHaveBeenCalledWith('EFGH');
    expect(openStockView).not.toHaveBeenCalled();
  });

  it('is plain text where there is no Trader to open', () => {
    render(<TickerLink symbol="IJKL" className="sym" />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('IJKL').className).toBe('sym');
  });
});
