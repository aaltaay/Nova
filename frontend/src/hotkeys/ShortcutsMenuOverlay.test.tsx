/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ShortcutsMenuOverlay } from './ShortcutsMenuOverlay';
import type { ShortcutCatalogSection } from './shortcutsCatalog';

const menuSection: ShortcutCatalogSection = {
  id: 'menu',
  title: 'Keyboard shortcuts',
  rows: [
    {
      id: 'menu:shortcuts_menu',
      chord: 'Ctrl+Alt',
      label: 'Show this menu',
      rebind: { type: 'menu' },
    },
  ],
};

const novaSection: ShortcutCatalogSection = {
  id: 'nova_actions',
  title: 'Nova Actions (System 2)',
  rows: [
    {
      id: 'nova-wb-sell-50-bid',
      chord: 'Ctrl+2',
      label: 'Sell 50% @BID -$0.03',
      detail: 'Sell long % at Bid – offset (limit)',
      rebind: { type: 'nova', id: 'nova-wb-sell-50-bid' },
      canEditAction: true,
      canDelete: true,
    },
  ],
};

const overlayDefaults = {
  occupied: [] as const,
  rebindTarget: null,
  rebindExcludeId: null,
  rebindConflict: null,
  onClosePinned: () => {},
  onApplyRebind: () => {},
  onRebindConflict: () => {},
  onCancelRebind: () => {},
};

describe('ShortcutsMenuOverlay rebind entry', () => {
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

  it('starts rebind from Key button and from double-click', () => {
    const onStartRebind = vi.fn();
    act(() => {
      root.render(
        <ShortcutsMenuOverlay
          mode="pinned"
          sections={[menuSection]}
          onStartRebind={onStartRebind}
          {...overlayDefaults}
        />,
      );
    });

    const keyBtn = container.querySelector('[data-testid="shortcuts-menu-key-btn"]');
    expect(keyBtn).toBeTruthy();
    expect(keyBtn?.textContent).toBe('Key');
    act(() => {
      (keyBtn as HTMLButtonElement).click();
    });
    expect(onStartRebind).toHaveBeenCalledWith(
      { type: 'menu' },
      'menu:shortcuts_menu',
    );

    onStartRebind.mockClear();
    const row = container.querySelector('.shortcuts-menu-row');
    act(() => {
      row?.dispatchEvent(
        new MouseEvent('dblclick', { bubbles: true, cancelable: true }),
      );
    });
    expect(onStartRebind).toHaveBeenCalledWith(
      { type: 'menu' },
      'menu:shortcuts_menu',
    );
  });

  it('exposes Edit and a two-step delete on Nova Action rows only', () => {
    const onStartRebind = vi.fn();
    const onEditAction = vi.fn();
    const onDeleteAction = vi.fn();
    act(() => {
      root.render(
        <ShortcutsMenuOverlay
          mode="pinned"
          sections={[menuSection, novaSection]}
          onStartRebind={onStartRebind}
          onEditAction={onEditAction}
          onDeleteAction={onDeleteAction}
          {...overlayDefaults}
        />,
      );
    });

    const menuRow = container.querySelectorAll('.shortcuts-menu-row')[0];
    expect(menuRow.querySelector('[data-testid="shortcuts-menu-edit-btn"]')).toBeNull();
    expect(menuRow.querySelector('[data-testid="shortcuts-menu-delete-btn"]')).toBeNull();

    const novaRow = container.querySelectorAll('.shortcuts-menu-row')[1];
    const edit = novaRow.querySelector('[data-testid="shortcuts-menu-edit-btn"]');
    expect(edit?.textContent).toBe('Edit');
    act(() => {
      (edit as HTMLButtonElement).click();
    });
    expect(onEditAction).toHaveBeenCalledWith('nova-wb-sell-50-bid');
    expect(onStartRebind).not.toHaveBeenCalled();

    const trash = novaRow.querySelector(
      '[data-testid="shortcuts-menu-delete-btn"]',
    ) as HTMLButtonElement;
    expect(trash).toBeTruthy();
    act(() => {
      trash.click();
    });
    expect(onDeleteAction).not.toHaveBeenCalled();
    act(() => {
      trash.click();
    });
    expect(onDeleteAction).toHaveBeenCalledTimes(1);
    expect(onDeleteAction).toHaveBeenCalledWith('nova-wb-sell-50-bid');
  });
});
