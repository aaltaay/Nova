import { expect, test, type Page } from '@playwright/test';
import { closed, day, T } from '../src/followed_traders/followedTestData';
import type { FollowedDay } from '../src/followed_traders/types';

// The Following page in a browser, its API answered here: it fits the desk's window with no page scrollbar, folds a
// busy day instead of scrolling, opens a trade's Proof from the Activity, and plays the stream (operator, 2026-10-13).
const PIXEL = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64');

async function open(page: Page, answer: FollowedDay) {
  const mutations: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('https://www.youtube-nocookie.com/**', (route) => route.fulfill({ contentType: 'text/html', body: '<body style="background:#111"></body>' }));
  await page.route('http://127.0.0.1:8999/**', async (route) => {
    const req = route.request();
    if (req.method() !== 'GET') mutations.push(req.url());
    const url = new URL(req.url());
    if (url.pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/png', body: PIXEL });
    if (url.pathname === '/api/followed-traders/day') return route.fulfill({ json: answer });
    if (url.pathname === '/api/followed-traders/reads') {
      return route.fulfill({ json: { schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, date: '2026-10-13',
        trader: 'ALPHA', available: false, why: 'The feed keeps no read log for that day', reads: [], truncated: false } });
    }
    return route.fulfill({ status: 404, body: '' });
  });
  await page.goto('/e2e/fixtures/following.html');
  await expect(page.getByTestId('ft-trader-ALPHA')).toBeVisible();
  return { mutations, errors };
}

async function fit(page: Page) {
  return page.evaluate(() => {
    const p = document.querySelector('.ft-page')!;
    const s = document.querySelector('.ft-stack')!;
    return { page: p.scrollHeight - p.clientHeight, doc: document.documentElement.scrollHeight - window.innerHeight,
      stack: s.scrollHeight - s.clientHeight, level: Number(s.getAttribute('data-fit-level')) };
  });
}

test.describe('Following page', () => {
  test('fits the desk window with no page scrollbar', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1720, height: 1104 });
    const { mutations, errors } = await open(page, day());
    await expect(page.getByTestId('ft-row-o1')).toContainText('OPEN');
    await expect(page.getByTestId('ft-row-c1')).toContainText('WIN');
    expect(await fit(page)).toEqual({ page: 0, doc: 0, stack: 0, level: 0 });
    await page.screenshot({ path: testInfo.outputPath('following.png') });
    expect(mutations).toEqual([]);
    expect(errors).toEqual([]);
  });

  test('a busy day shrinks closed rows and folds the oldest, never a scrollbar', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1720, height: 760 });
    const d = day();
    d.traders[0].closed = Array.from({ length: 14 }, (_, i) => closed({ id: `busy${i}`, symbol: `S${i}`,
      entry: { first_price: 2, avg_price: 2, ts: T - 3600 + i * 60, since_ts: null, known: true } }));
    const { errors } = await open(page, d);
    const earlier = page.getByTestId('ft-closed-earlier');
    await expect(earlier).toBeVisible();
    const f = await fit(page);
    expect(f.level).toBeGreaterThan(1);
    expect([f.page, f.doc, f.stack]).toEqual([0, 0, 0]);
    await page.screenshot({ path: testInfo.outputPath('following-busy.png') });
    await earlier.click();
    const all = page.getByTestId('ft-closed-all');
    await expect(all).toBeVisible();
    await expect(all.locator('[data-testid^="ft-row-busy"]')).toHaveCount(14);
    expect(errors).toEqual([]);
  });

  test('an Activity event opens its trade’s Proof, and back returns', async ({ page }) => {
    await page.setViewportSize({ width: 1720, height: 1104 });
    await open(page, day());
    await page.getByTestId('ft-activity-c1|out').click();
    await expect(page.getByTestId('ft-proof')).toBeVisible();
    await page.getByTestId('ft-proof-back').click();
    await expect(page.getByTestId('ft-trader-ALPHA')).toBeVisible();
  });

  test('plays the stream from YouTube’s privacy-enhanced host, closes it, and Watch live brings it back', async ({ page }) => {
    await page.setViewportSize({ width: 1720, height: 1104 });
    const d = day();
    d.capture = { ...d.capture!, video_id: 'R5YIugCJar0' };
    await open(page, d);
    await expect(page.getByTestId('ft-stream-frame')).toHaveAttribute('src', /^https:\/\/www\.youtube-nocookie\.com\/embed\/R5YIugCJar0\?autoplay=1&mute=1/);
    expect((await fit(page)).page).toBe(0);
    await page.getByTestId('ft-stream-close').click();
    await expect(page.getByTestId('ft-stream')).toHaveCount(0);
    await page.getByTestId('ft-watch-live').click();
    await expect(page.getByTestId('ft-stream')).toBeVisible();
  });

  test('off air plays no past broadcast, and today says when it resets', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1720, height: 1104 });
    const d = day({ resets_at: Date.UTC(2026, 9, 14, 8, 0, 0) / 1000 });
    // The feed's status still names the day's stream as live, five hours after its last read.
    d.capture = { ...d.capture!, video_id: 'R5YIugCJar0', clock: '15:57:12', age_sec: 18_000 };
    const { errors } = await open(page, d);
    await expect(page.getByTestId('ft-stream-offline')).toContainText('last read 15:57:12 ET');
    await expect(page.getByTestId('ft-stream-frame')).toHaveCount(0);
    // The display keeps its size: the same 16:9 screen the video plays in.
    const screen = (await page.locator('.ft-stream__screen').boundingBox())!;
    expect(screen.width / screen.height).toBeCloseTo(16 / 9, 1);
    await expect(page.getByTestId('ft-watch-live')).toBeDisabled();
    await expect(page.getByTestId('ft-day-reset')).toHaveText('Resets 4:00 AM ET');
    expect(await fit(page)).toEqual({ page: 0, doc: 0, stack: 0, level: 0 });
    await page.screenshot({ path: testInfo.outputPath('following-off-air.png') });
    expect(errors).toEqual([]);
  });
});
