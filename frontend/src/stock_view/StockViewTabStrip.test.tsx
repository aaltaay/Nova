/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockViewTabStrip } from './StockViewTabStrip';

describe('StockViewTabStrip', () => {
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

  it('extract button and double-click pop the tab out -- + stays in this window', async () => {
    const onExtract = vi.fn();
    const onAddDraft = vi.fn();
    const onActivate = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['SPY', 'IPST']}
          active="SPY"
          onActivate={onActivate}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={onAddDraft}
          onExtract={onExtract}
        />,
      );
    });
    const label = container.querySelector('[data-testid="sv-tab-SPY"] .sv-tab__label') as HTMLButtonElement;
    expect(label.title).toMatch(/Double-click to pop out/i);
    const extract = container.querySelector('[data-testid="sv-tab-extract-SPY"]') as HTMLButtonElement;
    expect(extract).toBeTruthy();
    expect(extract.getAttribute('aria-label')).toMatch(/new window/i);
    await act(async () => {
      extract.click();
    });
    expect(onExtract).toHaveBeenCalledWith('SPY');
    await act(async () => {
      label.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    expect(onExtract).toHaveBeenCalledWith('SPY');
    expect(onExtract).toHaveBeenCalledTimes(2);
    const hint = container.querySelector('[data-testid="sv-tab-strip-hint"]');
    expect(hint?.textContent).toMatch(/Drag a tab onto another Nova window/i);
    const add = container.querySelector('[data-testid="sv-tab-add"]') as HTMLButtonElement;
    expect(add.title).toMatch(/this window/i);
    await act(async () => {
      add.click();
    });
    expect(onAddDraft).toHaveBeenCalledOnce();
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('makes live tabs draggable and shows Dock only when asked', async () => {
    const onDock = vi.fn();
    const onTabDragStart = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['IPST']}
          active="IPST"
          windowId="float-1"
          showDock
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={vi.fn()}
          onDock={onDock}
          onTabDragStart={onTabDragStart}
        />,
      );
    });
    const tab = container.querySelector('[data-testid="sv-tab-IPST"]') as HTMLElement;
    expect(tab.getAttribute('draggable')).toBe('true');
    const dock = container.querySelector('[data-testid="sv-tab-dock-IPST"]') as HTMLButtonElement;
    expect(dock).toBeTruthy();
    await act(async () => {
      dock.click();
    });
    expect(onDock).toHaveBeenCalledWith('IPST');
  });

  it('hides Pop out on a float surface and does not extract on double-click', async () => {
    const onExtract = vi.fn();
    const onDock = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['F']}
          active="F"
          windowId="float-1"
          showDock
          showExtract={false}
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={onExtract}
          onDock={onDock}
        />,
      );
    });
    expect(container.querySelector('[data-testid="sv-tab-extract-F"]')).toBeNull();
    expect(container.querySelector('[data-testid="sv-tab-dock-F"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sv-tab-F"] .sv-tab__close')).toBeTruthy();
    const label = container.querySelector('[data-testid="sv-tab-F"] .sv-tab__label') as HTMLButtonElement;
    expect(label.title).not.toMatch(/pop out/i);
    await act(async () => {
      label.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    expect(onExtract).not.toHaveBeenCalled();
  });

  it('renders tabs, marks active, and disables add at cap', async () => {
    const onAddDraft = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['AAPL', 'NUWE', 'MVO']}
          active="NUWE"
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={onAddDraft}
          onExtract={vi.fn()}
        />,
      );
    });
    expect(container.querySelector('[data-testid="sv-tab-NUWE"]')?.className).toContain(
      'sv-tab--active',
    );
    const add = container.querySelector('[data-testid="sv-tab-add"]') as HTMLButtonElement;
    expect(add.disabled).toBe(true);
  });
});
