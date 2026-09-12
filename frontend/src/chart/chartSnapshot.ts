/**
 * "Snapshot" -- save the pane as a PNG using Lightweight Charts' own
 * `takeScreenshot()`. No server round trip, no third-party capture.
 */
import type { IChartApi } from 'lightweight-charts';

export function chartSnapshotFilename(
  symbol: string,
  timeframe: string,
  now: Date,
): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const sym = symbol.trim().toUpperCase() || 'CHART';
  const tf = timeframe.trim().replace(/[^A-Za-z0-9]/g, '') || 'tf';
  return `nova-${sym}-${tf}-${stamp}.png`;
}

export function downloadChartSnapshot(
  chart: IChartApi | null,
  symbol: string,
  timeframe: string,
  now: Date = new Date(),
): boolean {
  if (!chart || typeof chart.takeScreenshot !== 'function') return false;
  try {
    const canvas = chart.takeScreenshot();
    if (!canvas || typeof canvas.toDataURL !== 'function') return false;
    const link = document.createElement('a');
    link.href = canvas.toDataURL('image/png');
    link.download = chartSnapshotFilename(symbol, timeframe, now);
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
    return true;
  } catch (err) {
    console.warn('chart snapshot: capture failed', symbol, timeframe, err);
    return false;
  }
}
