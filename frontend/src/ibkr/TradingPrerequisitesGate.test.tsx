/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TradingPrerequisitesGate } from './TradingPrerequisitesGate';
import { openTradingPrerequisites } from './tradingPrereqUi';
import type { DiagnosticsPayload } from './diagnosticsTypes';

const status = vi.hoisted(() => ({
  connected: true,
  known: true,
  enabled: true,
  completed_orders_unanswered_since: null as number | null,
  gateway_read_only: false,
  recording: false,
}));

vi.mock('../components/scannerBarStore', () => ({
  useScannerBarProps: () => ({
    health: { status: 'connected', latency_ms: 5 },
    discoveryProvider: 'ibkr',
  }),
}));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    ibkrConnected: status.connected,
    ibkrGatewayMode: 'live',
    ibkrStatusKnown: status.known,
  }),
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: status.enabled,
    connected: status.connected,
    mode: 'live',
    stale: false,
    completed_orders_unanswered_since: status.completed_orders_unanswered_since,
    gateway_read_only: status.gateway_read_only,
  }),
  refreshIbkrStatusNow: () => {},
}));
vi.mock('./usePrereqOverlayInputs', () => ({
  usePrereqOverlayInputs: () => ({
    apiFailStreak: 0,
    deskActionInFlight: false,
    sessionRecording: status.recording,
  }),
}));
vi.mock('./GatewayDoorTrail', () => ({ GatewayDoorTrail: () => null }));
const diagnostics = vi.hoisted(() => ({ data: null as DiagnosticsPayload | null }));
vi.mock('./useDiagnostics', () => ({
  useDiagnostics: () => ({ data: diagnostics.data, error: null, loading: false, refresh: () => {} }),
  fetchDiagnosticsBundle: async () => '',
}));

describe('TradingPrerequisitesGate D-058 warning', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    status.connected = true;
    status.known = true;
    status.enabled = true;
    status.recording = false;
    status.completed_orders_unanswered_since = null;
    status.gateway_read_only = false;
    diagnostics.data = null;
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

  it('keeps a manually opened checklist visible when recording starts', () => {
    openPanel();
    expect(container.querySelector('.trading-prereq-gate')).not.toBeNull();
    status.recording = true;
    act(() => root.render(<TradingPrerequisitesGate />));
    expect(container.querySelector('.trading-prereq-gate')).not.toBeNull();
  });

  it('leads with every non-OK diagnostics row and the amber warnings, above the full checklist', () => {
    status.completed_orders_unanswered_since = 1789808049;
    const base = { cause: 'c', fix: 'f', since: null, action: null, evidence: null };
    diagnostics.data = {
      schema_version: 1,
      generated_at: 1790210000,
      groups: [{ id: 'gateway', title: 'Gateway' }],
      counts: { ok: 1, warn: 1 },
      rows: [
        { ...base, id: 'gateway_port', group: 'gateway', title: 'Gateway API port', state: 'ok', detail: 'answers' },
        { ...base, id: 'gateway_last_error', group: 'gateway', title: 'Last IB error', state: 'warn', detail: 'error 165' },
      ],
    };
    openPanel();
    const attention = container.querySelector('[data-testid="diag-attention"]');
    const warning = container.querySelector('[data-testid="trading-prereq-warning-completed_orders"]');
    const lead = container.querySelector('.trading-prereq-gate__lead');
    const checklist = container.querySelector('[data-testid="diagnostics-checklist"]');
    expect(attention?.textContent).toContain('Last IB error');
    expect(attention?.textContent).not.toContain('Gateway API port');
    const before = (a: Element | null, b: Element | null) =>
      Boolean(a && b && a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(before(attention, warning)).toBe(true);
    expect(before(warning, lead)).toBe(true);
    expect(before(lead, checklist)).toBe(true);
    // The duplicate is deliberate: the row stays in its group too.
    expect(container.querySelector('[data-testid="diag-row-gateway_last_error"]')).not.toBeNull();
  });

  it('shows the amber warning over an all-OK checklist', () => {
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

  it('names Read-Only API as its own red row (D-076)', () => {
    status.gateway_read_only = true;
    openPanel();
    const row = container.querySelector('[data-testid="trading-prereq-gateway_read_only"]');
    expect(row?.className).toMatch(/trading-prereq-item--bad/);
    expect(row?.textContent).toMatch(/Read-Only API/);
    // The Gateway row itself stays green -- this is not a login problem.
    expect(container.querySelector('[data-testid="trading-prereq-ibkr_gateway"]')?.className)
      .toMatch(/trading-prereq-item--ok/);
  });

  it('says IBKR is unknown, with no fix to apply, before the status answers (QA D10, #459)', () => {
    // The poller's default before any answer: disconnected and `enabled: false`.
    status.known = false;
    status.connected = false;
    status.enabled = false;
    openPanel();
    for (const id of ['ibkr_enabled', 'ibkr_gateway']) {
      const row = container.querySelector(`[data-testid="trading-prereq-${id}"]`);
      expect(row?.className, id).toMatch(/trading-prereq-item--unknown/);
      expect(row?.querySelector('.trading-prereq-item__mark')?.textContent, id).toBe('?');
      expect(row?.textContent, id).toMatch(/Unknown until Nova API answers/);
      expect(row?.querySelector('.trading-prereq-item__cta'), id).toBeNull();
    }
    expect(container.textContent).not.toMatch(/Set IBKR_ENABLED/);
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
