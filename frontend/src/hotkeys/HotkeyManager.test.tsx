/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  HOTKEY_MANAGER_INACTIVE_BANNER,
  HOTKEYS_CREATE_DIALOG_TITLE,
  HOTKEYS_SETTINGS_CTA,
  HOTKEYS_SETTINGS_DIALOG_TITLE,
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

  it('shows landing CTA, summary list, and active Nova shortcuts', () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    expect(container.textContent).toContain(HOTKEYS_SETTINGS_CTA);
    expect(container.querySelector('[data-testid="hotkeys-landing-list"]')).toBeTruthy();
    expect(container.textContent).toContain('Active Nova shortcuts');
    expect(container.textContent).toContain('Approve first staged bracket');
    const advanced = container.querySelector(
      '[data-testid="hotkeys-advanced-das"]',
    ) as HTMLDetailsElement;
    expect(advanced.open).toBe(false);
  });


  it('opens Hotkeys Settings from CTA and closes on Escape', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    const cta = container.querySelector(
      '[data-testid="hotkeys-settings-cta"]',
    ) as HTMLButtonElement;
    await act(async () => {
      cta.click();
    });
    expect(container.textContent).toContain(HOTKEYS_SETTINGS_DIALOG_TITLE);
    expect(container.querySelector('[data-testid="hotkeys-settings-dialog"]')).toBeTruthy();

    await act(async () => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(container.querySelector('[data-testid="hotkeys-settings-dialog"]')).toBeNull();
  });

  it('requires a second click to delete a Nova Action in settings', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-settings-cta"]') as HTMLButtonElement).click();
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

  it('creates a customized button from + and appends to list', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-settings-cta"]') as HTMLButtonElement).click();
    });
    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-settings-add"]') as HTMLButtonElement).click();
    });
    expect(container.textContent).toContain(HOTKEYS_CREATE_DIALOG_TITLE);

    const nameInput = container.querySelector(
      '[data-testid="hotkeys-create-name"]',
    ) as HTMLInputElement;
    await act(async () => {
      fireEvent.change(nameInput, { target: { value: 'My Ask Entry' } });
    });

    await act(async () => {
      (container.querySelector('[data-testid="hotkeys-create-submit"]') as HTMLButtonElement).click();
    });
    expect(container.querySelector('[data-testid="hotkeys-create-dialog"]')).toBeNull();
    expect(container.textContent).toContain('My Ask Entry');
  });


  it('hides unused category tabs and Coming soon chrome', () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    expect(container.querySelector('[role="tablist"]')).toBeNull();
    expect(container.querySelector('[data-testid="hotkeys-tab-soon"]')).toBeNull();
    expect(container.textContent).not.toContain('Coming soon');
    expect(container.textContent).not.toContain('Paper Trading');
    expect(container.querySelector('[data-testid="hotkeys-settings-cta"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="hotkeys-landing-list"]')).toBeTruthy();
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
    expect(container.querySelector('[data-testid="hotkeys-landing"]')).toBeTruthy();
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
