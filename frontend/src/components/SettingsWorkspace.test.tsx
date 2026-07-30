/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsWorkspace } from './SettingsWorkspace';
import type { ExchangeFilter } from '../hooks/useExchangeFilter';

vi.mock('../hotkeys/HotkeyManager', () => ({
  HotkeyManager: () => <div data-testid="hotkey-manager-mock">Hotkey Manager Mock</div>,
}));

vi.mock('./AlertChannelsSettings', () => ({
  AlertChannelsSettings: () => <div data-testid="alerts-mock">Alerts Mock</div>,
}));

vi.mock('../settings/TradeSettingsSection', () => ({
  TradeSettingsSection: () => <div data-testid="trade-mock">Trade Mock</div>,
}));

vi.mock('../settings/AccountSettingsSection', () => ({
  AccountSettingsSection: () => <div data-testid="account-mock">Account Mock</div>,
}));

vi.mock('../settings/GeneralSettingsSection', () => ({
  GeneralSettingsSection: () => <div data-testid="general-mock">General Mock</div>,
}));

const filter: ExchangeFilter = {
  selected: ['NASDAQ'],
  toggle: vi.fn(),
  selectAll: vi.fn(),
  filterRows: (rows) => rows,
};

const baseProps = {
  filter,
  apiKey: 'k',
  onApiKeyChange: vi.fn(),
  apiSecret: 's',
  onApiSecretChange: vi.fn(),
  baseUrl: 'http://localhost',
  onBaseUrlChange: vi.fn(),
  dataFeed: 'iex',
  onDataFeedChange: vi.fn(),
  dataFeedOptions: ['iex'],
  discoveryProvider: 'ibkr',
  onSubmit: vi.fn((e: { preventDefault: () => void }) => e.preventDefault()),
  onCancel: vi.fn(),
};

describe('SettingsWorkspace', () => {
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

  it('shows General by default and switches to Hot Keys', () => {
    act(() => {
      root.render(<SettingsWorkspace {...baseProps} />);
    });
    expect(container.querySelector('[data-testid="general-mock"]')).toBeTruthy();
    const hotkeysBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Hot Keys',
    );
    act(() => {
      hotkeysBtn?.click();
    });
    expect(container.querySelector('[data-testid="hotkey-manager-mock"]')).toBeTruthy();
    expect(hotkeysBtn?.classList.contains('active')).toBe(true);
  });

  it('switches to Trade, Alerts, and Account', () => {
    act(() => {
      root.render(<SettingsWorkspace {...baseProps} />);
    });
    for (const [label, testId] of [
      ['Trade', 'trade-mock'],
      ['Alerts', 'alerts-mock'],
      ['Account', 'account-mock'],
    ] as const) {
      const btn = Array.from(container.querySelectorAll('button')).find(
        (b) => b.textContent === label,
      );
      act(() => {
        btn?.click();
      });
      expect(container.querySelector(`[data-testid="${testId}"]`)).toBeTruthy();
    }
  });

  it('closes on Escape', () => {
    act(() => {
      root.render(<SettingsWorkspace {...baseProps} />);
    });
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(baseProps.onCancel).toHaveBeenCalled();
  });
});
