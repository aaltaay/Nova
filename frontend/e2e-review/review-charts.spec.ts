import fs from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

const BANNED = ['/api/ibkr', '/api/ticker', '/api/chart-drawings', '/api/orders', '/api/bot'];
const SYMBOLS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'];

function watch(page: Page): string[] {
  const urls: string[] = [];
  page.on('request', (req) => urls.push(req.url()));
  page.on('websocket', (ws) => urls.push(ws.url()));
  return urls;
}

function assertDeskQuiet(urls: string[]) {
  for (const url of urls) {
    for (const banned of BANNED) {
      expect(url, url).not.toContain(banned);
    }
    expect(url.startsWith('ws:') || url.startsWith('wss:'), url).toBe(false);
  }
}

test('fixture review page mounts the desk grid', async ({ page }) => {
  const urls = watch(page);
  await page.goto('/review?symbol=IMCC&date=2026-09-18&fixture=1');
  await expect(page.locator('[data-review-ready="1"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="chart-grid"]')).toHaveCount(1);
  for (const timeframe of ['10Sec', '1Min', '5Min', '1Day']) {
    await expect(page.locator(`[data-testid="ticker-chart-${timeframe}"]`)).toHaveCount(1);
  }
  assertDeskQuiet(urls);
  await page.screenshot({ path: '/opt/cursor/artifacts/review-imcc-desk-grid.png' });
});

test('nine symbol gallery switches timeframe without another review fetch', async ({ page }) => {
  const urls = watch(page);
  const coldStart = Date.now();
  await page.goto(`/review?symbols=${SYMBOLS.join(',')}&date=2026-09-18&fixture=1`);
  await expect(page.locator('[data-review-ready="1"]')).toBeVisible({ timeout: 30_000 });
  const coldMs = Date.now() - coldStart;
  await expect(page.locator('[data-testid="ticker-chart-5Min"]')).toHaveCount(9);

  const reviewFetches = () => urls.filter((url) => url.includes('/api/review')).length;
  const before = reviewFetches();
  const tabs = [
    ['10s', '10Sec'],
    ['1m', '1Min'],
    ['5m', '5Min'],
    ['1d', '1Day'],
  ] as const;
  for (const [gtf, timeframe] of tabs) {
    await page.getByTestId(`review-tab-${gtf}`).click();
    await expect(page).toHaveURL(new RegExp(`[?&]gtf=${gtf}(?:&|$)`));
    await expect(page.locator('[data-review-ready="1"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(`[data-testid="ticker-chart-${timeframe}"]`)).toHaveCount(9);
    await expect(page.locator('[data-testid^="ticker-chart-"]')).toHaveCount(9);
  }
  expect(reviewFetches()).toBe(before);
  assertDeskQuiet(urls);

  const warmStart = Date.now();
  await page.reload();
  await expect(page.locator('[data-review-ready="1"]')).toBeVisible({ timeout: 30_000 });
  const warmMs = Date.now() - warmStart;
  fs.mkdirSync('/opt/cursor/artifacts', { recursive: true });
  fs.writeFileSync(
    '/opt/cursor/artifacts/review-gallery-timing.json',
    JSON.stringify({ coldMs, warmMs, viewport: '1920x1080', symbols: 9 }, null, 2),
  );
  await page.screenshot({ path: '/opt/cursor/artifacts/review-gallery-9.png' });
});
