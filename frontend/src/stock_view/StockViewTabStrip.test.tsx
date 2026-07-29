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
