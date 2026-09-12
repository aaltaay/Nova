/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import type { IChartApi } from 'lightweight-charts';
import { chartSnapshotFilename, downloadChartSnapshot } from './chartSnapshot';

describe('chartSnapshotFilename', () => {
  it('stamps symbol, timeframe and local time', () => {
    expect(
      chartSnapshotFilename('smpl', '10Sec', new Date(2026, 8, 12, 9, 31, 5)),
    ).toBe('nova-SMPL-10Sec-20260912-093105.png');
  });
});

describe('downloadChartSnapshot', () => {
  it('saves the Lightweight Charts screenshot as a PNG', () => {
    const toDataURL = vi.fn(() => 'data:image/png;base64,AAA');
    const chart = {
      takeScreenshot: () => ({ toDataURL }) as unknown as HTMLCanvasElement,
    } as unknown as IChartApi;
    const clicked: string[] = [];
    const realClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function click(this: HTMLAnchorElement) {
      clicked.push(this.download);
    };

    expect(downloadChartSnapshot(chart, 'SMPL', '5Min')).toBe(true);
    expect(toDataURL).toHaveBeenCalledWith('image/png');
    expect(clicked[0]).toMatch(/^nova-SMPL-5Min-\d{8}-\d{6}\.png$/);
    expect(document.querySelector('a[download]')).toBeNull();

    HTMLAnchorElement.prototype.click = realClick;
  });

  it('returns false when the chart cannot capture', () => {
    expect(downloadChartSnapshot(null, 'SMPL', '5Min')).toBe(false);
    expect(
      downloadChartSnapshot({} as unknown as IChartApi, 'SMPL', '5Min'),
    ).toBe(false);
  });
});
