/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ShortcutsMenuOverlay } from './ShortcutsMenuOverlay';
import type { ShortcutCatalogSection } from './shortcutsCatalog';

const sections: ShortcutCatalogSection[] = [
  {
    id: 'menu',
    title: 'Keyboard shortcuts',
    rows: [
      {
        id: 'menu:shortcuts_menu',
        chord: 'Ctrl+M',
        label: 'Show this menu',
        rebind: { type: 'menu' },
      },
    ],
  },
];

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

  it('starts rebind from Edit button and from double-click', () => {
    const onStartRebind = vi.fn();
    act(() => {
      root.render(
        <ShortcutsMenuOverlay
          mode="pinned"
          sections={sections}
          occupied={[]}
          rebindTarget={null}
          rebindExcludeId={null}
          rebindConflict={null}
          onClosePinned={() => {}}
          onStartRebind={onStartRebind}
          onApplyRebind={() => {}}
          onRebindConflict={() => {}}
          onCancelRebind={() => {}}
        />,
      );
    });

    const edit = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Edit',
    );
    expect(edit).toBeTruthy();
    act(() => {
      edit?.click();
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
});
