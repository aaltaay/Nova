/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  HOTKEY_MANAGER_INACTIVE_BANNER,
  HOTKEYS_CREATE_APPLY_LOCKED_WHY,
  HOTKEYS_CREATE_DIALOG_TITLE,
  HOTKEYS_SETTINGS_LIST_TITLE,
} from '../constants';
import { HotkeyManager } from './HotkeyManager';
import { serializeHtk } from './htkFormat';


function openAdvancedDas(container: HTMLElement) {
  const details = container.querySelector(
    '[data-testid="hotkeys-advanced-das"]',
  ) as HTMLDetailsElement | null;
  expect(details).toBeTruthy();
  act(() => {
    details!.open = true;
    details!.dispatchEvent(new Event('toggle', { bubbles: true }));
  });
}

function listRows(container: HTMLElement): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll<HTMLButtonElement>('.hk-editor-row'));
}

describe('HotkeyManager', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
  });

  it('renders the two-pane editor inline -- no dialog, no landing CTA', () => {
    act(() => {
      root.render(<HotkeyManager onDone={() => {}} />);
    });
    expect(container.querySelector('[data-testid="hotkeys-settings-editor"]')).toBeTruthy();
    expect(container.textContent).toContain(HOTKEYS_SETTINGS_LIST_TITLE);
    expect(listRows(container).length).toBeGreaterThan(0);
    expect(container.querySelector('[data-testid="hotkeys-settings-detail"]')).toBeTruthy();
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelector('[aria-modal="true"]')).toBeNull();
    expect(container.querySelector('[data-testid="hotkeys-settings-cta"]')).toBeNull();
    // The Automation six went with the Nova OS mode ladder (ADR 025).
    expect(container.textContent).not.toContain('Active Nova shortcuts');
    expect(container.textContent).not.toContain('Approve first staged bracket');
    const advanced = container.querySelector(
      '[data-testid="hotkeys-advanced-das"]',
    ) as HTMLDetailsElement;
    expect(advanced.open).toBe(false);
  });

  it('selects the first action, marks the row, and switches on click', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    const rows = listRows(container);
    expect(rows[0].classList.contains('is-selected')).toBe(true);
    expect(rows[0].getAttribute('aria-current')).toBe('true');
    // The list label is "<name> · <context>"; the detail title is the bare name.
    const detailTitle = () =>
      container.querySelector('[data-testid="hotkeys-settings-detail"] h3')?.textContent ?? '';
    const rowLabel = (row: HTMLButtonElement) =>
      row.querySelector('.hk-editor-row-name')?.textContent ?? '';
    expect(detailTitle().length).toBeGreaterThan(0);
    expect(rowLabel(rows[0]).startsWith(detailTitle())).toBe(true);

    await act(async () => {
      rows[1].click();
    });
    expect(listRows(container)[1].classList.contains('is-selected')).toBe(true);
    expect(listRows(container)[0].classList.contains('is-selected')).toBe(false);
    expect(rowLabel(rows[1]).startsWith(detailTitle())).toBe(true);
    expect(rowLabel(rows[1])).not.toBe(rowLabel(rows[0]));
  });

  it('Done hands back to Settings; Escape is not handled by the editor', async () => {
    const onDone = vi.fn();
    act(() => {
      root.render(<HotkeyManager onDone={onDone} />);
    });
    await act(async () => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(container.querySelector('[data-testid="hotkeys-settings-editor"]')).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();

    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-settings-done"]') as HTMLButtonElement).click();
    });
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('omits Done when nothing hands back', () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    expect(container.querySelector('[data-testid="hotkeys-settings-done"]')).toBeNull();
    expect(container.textContent).toContain('Reset to Default');
  });

  it('requires a second click to delete a Nova Action', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    expect(container.textContent).toContain('Cancel symbol orders');
    const trash = container.querySelector(
      '[data-testid="hotkeys-settings-delete-btn"]',
    ) as HTMLButtonElement;
    expect(trash).toBeTruthy();
    await act(async () => {
      trash.click();
    });
    expect(container.textContent).toContain('Cancel symbol orders');
    await act(async () => {
      trash.click();
    });
    expect(container.textContent).not.toContain('Cancel symbol orders');
  });

  it('+ opens the Create form in the right pane; Create appends and selects it', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    const before = listRows(container).length;
    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-settings-add"]') as HTMLButtonElement).click();
    });
    expect(container.textContent).toContain(HOTKEYS_CREATE_DIALOG_TITLE);
    expect(container.querySelector('[data-testid="hotkeys-create-form"]')).toBeTruthy();
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelector('[data-testid="hotkeys-settings-detail"]')).toBeNull();
    // Button Apply To is locked to Stock, and says why (ux/whyTip.ts).
    const applyTo = container.querySelector('[data-testid="hotkeys-create-apply"]') as HTMLSelectElement;
    expect(applyTo.disabled).toBe(true);
    expect(applyTo.dataset.why).toBe(HOTKEYS_CREATE_APPLY_LOCKED_WHY);

    const nameInput = container.querySelector(
      '[data-testid="hotkeys-create-name"]',
    ) as HTMLInputElement;
    await act(async () => {
      fireEvent.change(nameInput, { target: { value: 'My Ask Entry' } });
    });

    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-create-submit"]') as HTMLButtonElement).click();
    });
    expect(container.querySelector('[data-testid="hotkeys-create-form"]')).toBeNull();
    const rows = listRows(container);
    expect(rows.length).toBe(before + 1);
    const created = rows[rows.length - 1];
    expect(created.textContent).toContain('My Ask Entry');
    expect(created.classList.contains('is-selected')).toBe(true);
    expect(
      container.querySelector('[data-testid="hotkeys-settings-detail"] h3')?.textContent,
    ).toBe('My Ask Entry');
  });

  it('Cancel on the Create form returns to the selected action', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-settings-add"]') as HTMLButtonElement).click();
    });
    const cancel = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Cancel' && b.closest('[data-testid="hotkeys-create-form"]'),
    );
    await act(async () => {
      cancel?.click();
    });
    expect(container.querySelector('[data-testid="hotkeys-create-form"]')).toBeNull();
    expect(container.querySelector('[data-testid="hotkeys-settings-detail"]')).toBeTruthy();
  });

  it('hides unused category tabs and Coming soon chrome', () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    expect(container.querySelector('[role="tablist"]')).toBeNull();
    expect(container.querySelector('[data-testid="hotkeys-tab-soon"]')).toBeNull();
    expect(container.textContent).not.toContain('Coming soon');
    expect(container.textContent).not.toContain('Paper Trading');
    expect(container.querySelector('[data-testid="hotkeys-settings-list"]')).toBeTruthy();
  });

  it('imports .htk via Advanced DAS preview then replace without fetch', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    act(() => {
      root.render(<HotkeyManager />);
    });
    openAdvancedDas(container);
    expect(container.textContent).toContain(HOTKEY_MANAGER_INACTIVE_BANNER);

    const body = serializeHtk([
      {
        id: 'x',
        name: 'Yahoo Finance',
        key: { label: 'Alt+3', key: '3', alt: true },
        command: 'http://finance.yahoo.com/quote/%SYMB%',
      },
    ]);
    const file = new File([body], 'sample.htk', { type: 'text/plain' });
    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;

    await act(async () => {
      Object.defineProperty(input, 'files', {
        configurable: true,
        value: [file],
      });
      input.dispatchEvent(new Event('change', { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain('Import preview');
    const replaceBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Replace profile',
    );
    await act(async () => {
      replaceBtn?.click();
    });
    expect(container.textContent).toContain('Yahoo Finance');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('opens Help catalog from Advanced DAS', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    openAdvancedDas(container);
    const helpBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Help',
    );
    await act(async () => {
      helpBtn?.click();
    });
    expect(container.textContent).toContain('Hotkey capability help');
    const closeBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Close',
    );
    await act(async () => {
      closeBtn?.click();
    });
    expect(container.querySelector('[data-testid="hotkeys-section"]')).toBeTruthy();
  });

  it('maps a selected DAS cancel row to a disabled Nova Action without fetch', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    act(() => {
      root.render(<HotkeyManager />);
    });
    openAdvancedDas(container);
    const body = serializeHtk([
      {
        id: 'cxl',
        name: 'Cancel symb',
        key: { label: 'Shift+Backspace', key: 'Backspace', shift: true },
        command: 'CXL ALLSYMB',
      },
    ]);
    const file = new File([body], 'sample.htk', { type: 'text/plain' });
    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;

    await act(async () => {
      Object.defineProperty(input, 'files', {
        configurable: true,
        value: [file],
      });
      input.dispatchEvent(new Event('change', { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });
    const replaceBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Replace profile',
    );
    await act(async () => {
      replaceBtn?.click();
    });

    const row = Array.from(container.querySelectorAll('tr')).find((tr) =>
      tr.textContent?.includes('Cancel symb'),
    );
    await act(async () => {
      row?.click();
    });

    const mapBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent?.includes('Map to Nova Action'),
    );
    expect(mapBtn).toBeTruthy();
    expect(mapBtn?.hasAttribute('disabled')).toBe(false);
    await act(async () => {
      mapBtn?.click();
    });
    expect(container.textContent).toContain('Map to Nova Action');

    const confirmBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Create Nova Action',
    );
    await act(async () => {
      confirmBtn?.click();
    });
    expect(container.textContent).toContain('disabled Nova Action');
    expect(container.textContent).toContain('Cancel symb');
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
