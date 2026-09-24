import type { Page } from '@playwright/test';

/**
 * Serve deterministic candles to a Trader tab on the live route.
 *
 * The e2e Vite server points at an API that is not running, so the chart
 * paints nothing and the price scale cannot convert a cursor Y into a price.
 * Routing `/bars` gives the chart a real series, which is what the right-click
 * menu prices its Buy / Sell rows from. It cannot feed `?view=sample`: the
 * sample desk refuses every backend read inside the page before it reaches the
 * network (src/sample_data/sampleNetworkGate.ts). See liveTraderApi.ts.
 */
const STEP_MS: Record<string, number> = {
  '10Sec': 10_000,
  '1Min': 60_000,
  '5Min': 300_000,
  '15Min': 900_000,
  '30Min': 1_800_000,
  '1Hour': 3_600_000,
  '1Day': 86_400_000,
};

export async function routeSampleBars(page: Page, count = 120): Promise<void> {
  await page.route('**/api/ticker/*/bars*', async (route) => {
    const timeframe =
      new URL(route.request().url()).searchParams.get('timeframe') ?? '1Min';
    const step = STEP_MS[timeframe] ?? 60_000;
    const start = Date.UTC(2026, 8, 11, 13, 30, 0) - count * step;
    const bars = Array.from({ length: count }, (_, i) => {
      const open = 4 + Math.sin(i / 6) * 0.3;
      const close = 4 + Math.sin((i + 1) / 6) * 0.3;
      return {
        t: new Date(start + i * step).toISOString(),
        o: Number(open.toFixed(2)),
        h: Number((Math.max(open, close) + 0.05).toFixed(2)),
        l: Number((Math.min(open, close) - 0.05).toFixed(2)),
        c: Number(close.toFixed(2)),
        v: 10_000 + i * 25,
      };
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ bars, coverage: null }),
    });
  });
}
