/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TradingPrerequisitesGate } from './TradingPrerequisitesGate';
import { openTradingPrerequisites } from './tradingPrereqUi';

const status = vi.hoisted(() => ({
  connected: true,
  completed_orders_unanswered_since: null as number | null,
}));

vi.mock('../components/scannerBarStore', () => ({
  useScannerBarProps: () => ({
    health: { status: 'connected', latency_ms: 5 },
    discoveryProvider: 'ibkr',
  }),
}));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ ibkrConnected: status.connected, ibkrGatewayMode: 'live' }),
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: status.connected,
    mode: 'live',
    stale: false,
    completed_orders_unanswered_since: status.completed_orders_unanswered_since,
  }),
  refreshIbkrStatusNow: () => {},
}));
vi.mock('./usePrereqOverlayInputs', () => ({
  usePrereqOverlayInputs: () => ({
    apiFailStreak: 0,
    deskActionInFlight: false,
    sessionRecording: false,
  }),
}));
vi.mock('./GatewayDoorTrail', () => ({ GatewayDoorTrail: () => null }));

describe('TradingPrerequisitesGate D-058 warning', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    status.connected = true;
    status.completed_orders_unanswered_since = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function openPanel() {
    act(() => root.render(<TradingPrerequisitesGate />));
    act(() => openTradingPrerequisites());
  }

  it('shows the amber warning under an all-OK checklist', () => {
    status.completed_orders_unanswered_since = 1789808049;
    openPanel();
    const warning = container.querySelector(
      '[data-testid="trading-prereq-warning-completed_orders"]',
    );
    expect(warning?.textContent).toMatch(/Completed orders not answering since/);
    expect(warning?.getAttribute('role')).toBe('status');
    const rows = container.querySelectorAll('.trading-prereq-item');
    expect(rows).toHaveLength(3);
    expect(container.querySelectorAll('.trading-prereq-item--bad')).toHaveLength(0);
  });

  it('renders no warning while completed orders answer', () => {
    openPanel();
    expect(container.querySelector('.trading-prereq-warning')).toBeNull();
    expect(container.querySelectorAll('.trading-prereq-item--ok')).toHaveLength(3);
  });

  it('keeps the Reconnect CTA working in the extracted row when READY is lost', () => {
    status.connected = false;
    status.completed_orders_unanswered_since = 1789808049;
    openPanel();
    expect(container.querySelector('.trading-prereq-warning')).toBeNull();
    expect(container.querySelector('[data-testid="trading-prereq-ibkr_gateway"]')?.className)
      .toMatch(/trading-prereq-item--bad/);
  });
});
