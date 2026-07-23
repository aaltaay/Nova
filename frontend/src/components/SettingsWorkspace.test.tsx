/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsWorkspace } from './SettingsWorkspace';

vi.mock('../hotkeys/HotkeyManager', () => ({
  HotkeyManager: () => <div data-testid="hotkey-manager-mock">Hotkey Manager Mock</div>,
}));

vi.mock('./AlertChannelsSettings', () => ({
  AlertChannelsSettings: () => <div data-testid="alerts-mock">Alerts Mock</div>,
}));

const baseProps = {
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

  it('shows General by default and switches to Hotkeys', () => {
    act(() => {
      root.render(<SettingsWorkspace {...baseProps} />);
    });
    const general = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'General',
    );
    expect(general?.classList.contains('active')).toBe(true);
    expect(container.textContent).toContain('Settings');

    const hotkeysBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Hotkeys',
    );
    act(() => {
      hotkeysBtn?.click();
    });
    expect(container.querySelector('[data-testid="hotkey-manager-mock"]')).toBeTruthy();
    expect(hotkeysBtn?.classList.contains('active')).toBe(true);
  });

  it('switches to Alerts section', () => {
    act(() => {
      root.render(<SettingsWorkspace {...baseProps} />);
    });
    const alertsBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Alerts',
    );
    act(() => {
      alertsBtn?.click();
    });
    expect(container.querySelector('[data-testid="alerts-mock"]')).toBeTruthy();
  });
});
