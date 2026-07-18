/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOTKEY_MANAGER_INACTIVE_BANNER } from '../constants';
import { HotkeyManager } from './HotkeyManager';
import { serializeHtk } from './htkFormat';

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

  it('shows inactive banner and active Nova shortcuts', () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
    expect(container.textContent).toContain(HOTKEY_MANAGER_INACTIVE_BANNER);
    expect(container.textContent).toContain('Active Nova shortcuts');
    expect(container.textContent).toContain('Approve first staged bracket');
  });

  it('imports .htk via preview then replace without fetch', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    act(() => {
      root.render(<HotkeyManager />);
    });
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

  it('opens Help catalog', async () => {
    act(() => {
      root.render(<HotkeyManager />);
    });
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
    expect(container.textContent).toContain(HOTKEY_MANAGER_INACTIVE_BANNER);
  });

  it('maps a selected DAS cancel row to a disabled Nova Action without fetch', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    act(() => {
      root.render(<HotkeyManager />);
    });
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
