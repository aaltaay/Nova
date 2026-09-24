/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeDetail } from '../modules/quoteFixtures';
import { TickerTradeSideColumn } from './TickerTradeSideColumn';

// Level 2 mounts only while IBKR is connected; these tests render it disconnected.
vi.mock('./DepthAndTape', () => ({ DepthAndTape: () => null }));

const REASON =
  'Float 8.45M is under half of the 142.37M shares not held by insiders (163.27M outstanding, 12.8% insiders) -- likely stale since a dilution';

describe('TickerTradeSideColumn float and short interest (#532)', () => {
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

  const stat = (label: string) =>
    [...container.querySelectorAll('.trade-side-stat')].find(
      (s) => s.querySelector('.trade-side-stat-label')?.textContent === label,
    ) as HTMLElement;

  it('marks a contradicted float and dates the short interest', () => {
    const base = makeDetail().fundamentals!;
    const detail = makeDetail({
      fundamentals: {
        ...base,
        float_shares: 8_450_000,
        shares_outstanding: 163_270_000,
        float_contradicted: true,
        float_contradicted_reason: REASON,
        short_interest: 3_760_000,
        short_interest_ts: Date.UTC(2026, 7, 31) / 1000,
        short_ratio: 1.4,
      },
    });
    act(() => {
      root.render(<TickerTradeSideColumn detail={detail} position={null} ibkrConnected={false} mode="paper" />);
    });
    expect(stat('Float').querySelector('.trade-side-stat-value')?.textContent).toBe('8.4M?');
    expect(stat('Float').title).toBe(REASON);
    expect(stat('Short int').querySelector('.trade-side-stat-value')?.textContent).toBe('3.8M (Aug 31)');
    expect(stat('Short int').title).toContain('FINRA settlement Aug 31, 2026');
    expect(stat('Short int').title).toContain("Short ratio 1.4 is Yahoo's own");
  });

  it('reads as before when the API sends no check or date', () => {
    act(() => {
      root.render(<TickerTradeSideColumn detail={makeDetail()} position={null} ibkrConnected={false} mode="paper" />);
    });
    expect(stat('Float').querySelector('.trade-side-stat-value')?.textContent).toBe('15.00B');
    expect(stat('Float').title).toBe('');
    expect(stat('Short int').querySelector('.trade-side-stat-value')?.textContent).toBe('100.0M');
  });
});
