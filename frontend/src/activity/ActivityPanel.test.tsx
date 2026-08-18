/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { ActivityPanel } from './ActivityPanel';
import type { ActivityRow } from './types';

const ROW: ActivityRow = {
  id: 'exec-1',
  created_ts: 1_700_000_000,
  operation: 'place',
  source: 'manual',
  symbol: 'IVF',
  side: 'BUY',
  requested_qty: 10,
  sent_qty: 1,
  forced_one_share: true,
  order_id: 19112,
  status: 'filled',
  broker_status: 'Filled',
  timings: {
    validation_ms: 0.5,
    persisted_ms: 1,
    broker_sent_ms: 2,
    broker_ack_ms: 3,
    filled_ms: 4,
  },
};

describe('ActivityPanel', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ ...ROW, fill_evidence: [] }),
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('shows requested vs sent qty and the 1-share flag', () => {
    act(() => {
      root.render(<ActivityPanel rows={[ROW]} />);
    });
    expect(container.querySelector('[data-testid="activity-panel"]')).toBeTruthy();
    expect(container.textContent).toContain('10 -> 1');
    expect(container.textContent).toContain('yes');
    expect(container.textContent).toContain('IVF');
  });

  it('keeps last-known rows under the error banner', () => {
    act(() => {
      root.render(<ActivityPanel rows={[ROW]} error="activity unavailable (HTTP 500)" />);
    });
    expect(container.querySelector('[data-testid="activity-error"]')).toBeTruthy();
    expect(container.textContent).toContain('IVF');
  });
});
