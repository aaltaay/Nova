/**
 * @vitest-environment jsdom
 *
 * Verifies the table's mounted DOM row count stays bounded (fixed-window
 * virtualization) even with a production-scale alert count, instead of the
 * old "batch-append on scroll" behavior that grew the DOM forever.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  HOD_MOMO_OVERSCAN_ROWS,
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_VISIBLE_ROWS,
} from '../constants';
import { HodMomoAlertTable } from './HodMomoAlertTable';
import type { AlertObject } from './types';

function makeAlerts(count: number): AlertObject[] {
  const alerts: AlertObject[] = [];
  for (let i = 0; i < count; i++) {
    alerts.push({
      id: `a${i}`,
      timestamp: new Date(1_700_000_000_000 + i * 1000).toISOString(),
      created_ts: 1_700_000_000 + i,
      ticker: `SYM${i}`,
      strategy_id: 3,
      strategy_name: 'Low Float - Med Rel Vol',
      price: 1 + i * 0.01,
      change_pct: 1,
      rvol: 2,
      float_shares: 1_000_000,
      gap_pct: null,
      volume: 1000,
      momentum_pct: null,
      rvol_source: 'ibkr_pace',
      consolidation_count: 1,
      consolidated_ids: [],
    });
  }
  return alerts;
}

const noop = () => {};
// Allow a little tolerance for the two spacer <tr>s and boundary rounding.
const MAX_MOUNTED_ROWS = HOD_MOMO_VISIBLE_ROWS + 2 * HOD_MOMO_OVERSCAN_ROWS + 2;

describe('HodMomoAlertTable virtualization', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    // jsdom does not implement Element.scrollTo — harmless no-op for this test.
    if (!Element.prototype.scrollTo) {
      Element.prototype.scrollTo = () => {};
    }
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('keeps mounted row count bounded with 5,000 alerts, not proportional to total', async () => {
    const alerts = makeAlerts(5_000);
    await act(async () => {
      root.render(
        <HodMomoAlertTable
          alerts={alerts}
          connected
          consolidationSec={10}
          configColors={{}}
          strategyCounts={{}}
          visibleStrategies={new Set([3])}
          onToggleStrategy={noop}
          selectedSymbol={null}
          onSelectSymbol={noop}
          onOpenTrading={noop}
        />,
      );
    });

    const wrapper = container.querySelector('.hod-table-wrapper') as HTMLDivElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper.getAttribute('data-total-count')).toBe('5000');

    const mountedAtTop = container.querySelectorAll('tr.hod-alert-row').length;
    expect(mountedAtTop).toBeGreaterThan(0);
    expect(mountedAtTop).toBeLessThanOrEqual(MAX_MOUNTED_ROWS);
    expect(container.textContent).toContain('SYM0');
    expect(container.textContent).not.toContain('SYM3000');

    // Scroll deep into a 5,000-row list — this used to be exactly the case
    // that made the old batch-append table mount thousands of rows. The
    // handler coalesces scroll events to one windowing update per animation
    // frame, so the test must let that frame run before asserting.
    await act(async () => {
      wrapper.scrollTop = 3_000 * HOD_MOMO_ROW_HEIGHT_PX;
      wrapper.dispatchEvent(new Event('scroll', { bubbles: true }));
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    });

    const mountedAfterScroll = container.querySelectorAll('tr.hod-alert-row').length;
    expect(mountedAfterScroll).toBeGreaterThan(0);
    expect(mountedAfterScroll).toBeLessThanOrEqual(MAX_MOUNTED_ROWS);
    // A different slice of data is now on screen — not stuck rendering the top.
    expect(container.textContent).toContain('SYM3000');
    expect(container.textContent).not.toContain('SYM0');
  });
});
