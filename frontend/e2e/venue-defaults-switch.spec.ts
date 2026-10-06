import { expect, test, type BrowserContext } from '@playwright/test';

type Venue = 'paper' | 'live' | 'sim';
const fixture = '/e2e/fixtures/venue-defaults-switch.html';

async function mockDesk(context: BrowserContext) {
  let venue: Venue = 'paper';
  let orderRequests = 0;
  await context.addInitScript(() => {
    if (!localStorage.getItem('nova.trade.defaults.migration.v1')) {
      localStorage.setItem('nova.trade.defaults.v1', JSON.stringify({
        v: 1, quantity: 17, tif: 'GTC', orderType: 'LMT', protectiveLegs: true,
      }));
    }
  });
  await context.route('http://127.0.0.1:8999/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === '/api/desk/venue') {
      venue = route.request().postDataJSON().venue as Venue;
      body = { ok: true, venue, left: [] };
    } else if (path === '/api/ibkr/status') {
      // Live on the legacy paper Gateway: mode must not own preferences.
      body = { enabled: true, connected: true, transport_connected: true,
        venue, mode: 'paper', spend_status: 'disarmed', orders_enabled: true };
    } else if (path === '/api/ibkr/gateway-mode') {
      body = { ok: true, mode: 'live', launch_action: 'noop' };
    } else if (path === '/api/bot/session') {
      body = { level_venue: venue, level: venue === 'paper' ? 2 : 0, armed: false,
        caps: { max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3,
          extended_hours: false, allowlist: [] }, working: [], focus: [], trader_live: [] };
    } else if (path.endsWith('/proposals')) {
      body = { proposals: [] };
    } else if (path.endsWith('/audit')) {
      body = { entries: [] };
    } else if (path === '/api/sim/clock') {
      body = { sim: venue === 'sim', paused: true, replay_source: 'none' };
    }
    if (/place|flatten/.test(path)) orderRequests += 1;
    await route.fulfill({ json: body });
  });
  return { orderRequests: () => orderRequests };
}

test('open Settings, ticket and bot follow explicit venues without carrying practice defaults to Live', async ({ page, context }) => {
  const api = await mockDesk(context);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(fixture);
  await expect(page.getByTestId('confirmed-venue')).toHaveText('paper');
  await expect(page.locator('#trade-def-tif')).toHaveValue('GTC');
  await expect(page.locator('#manual-order-quantity')).toHaveValue('17');
  await expect(page.getByTestId('bot-venue-level')).toHaveText('paper:2');

  await page.locator('#trade-def-qty').fill('31');
  await expect(page.locator('#manual-order-quantity')).toHaveValue('31');
  await page.getByTestId('gateway-mode-capsule-live').click();
  await expect(page.getByTestId('confirmed-venue')).toHaveText('live');
  await expect(page.locator('#trade-def-tif')).toHaveValue('DAY');
  await expect(page.locator('#trade-def-legs')).not.toBeChecked();
  await expect(page.locator('#manual-order-quantity')).toHaveValue('100');
  await expect(page.getByTestId('manual-order-tif-day')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('bot-venue-level')).toHaveText('live:0');

  await page.locator('#trade-def-qty').fill('3');
  await page.getByTestId('gateway-mode-capsule-paper').click();
  await expect(page.locator('#manual-order-quantity')).toHaveValue('31');
  await expect(page.locator('#trade-def-tif')).toHaveValue('GTC');
  await expect(page.locator('#trade-def-legs')).toBeChecked();
  await expect(page.getByTestId('bot-venue-level')).toHaveText('paper:2');
  const saved = await page.evaluate(() => ({
    legacy: localStorage.getItem('nova.trade.defaults.v1'),
    receipt: JSON.parse(localStorage.getItem('nova.trade.defaults.migration.v1')!),
    live: JSON.parse(localStorage.getItem('nova.trade.defaults.v2.live')!),
  }));
  expect(saved.legacy).toBeNull();
  expect(saved.receipt.venue).toBe('paper');
  expect(saved.live.prefs.quantity).toBe(3);
  expect(api.orderRequests()).toBe(0);
  expect(errors).toEqual([]);
});

test('a second mounted window receives venue and preference changes', async ({ page, context }) => {
  const api = await mockDesk(context);
  const peer = await context.newPage();
  const errors: string[] = [];
  for (const window of [page, peer]) window.on('pageerror', error => errors.push(error.message));
  await page.goto(fixture);
  await expect(page.getByTestId('bot-venue-level')).toHaveText('paper:2');
  await peer.goto(fixture);
  await expect(peer.locator('#trade-def-tif')).toHaveValue('GTC');
  await page.locator('#trade-def-qty').fill('23');
  await expect(peer.locator('#manual-order-quantity')).toHaveValue('23');
  await page.getByTestId('gateway-mode-capsule-live').click();
  await expect(peer.getByTestId('confirmed-venue')).toHaveText('live');
  await expect(peer.locator('#trade-def-tif')).toHaveValue('DAY');
  await expect(peer.getByTestId('bot-venue-level')).toHaveText('live:0');
  await peer.locator('#trade-def-qty').fill('4');
  await expect(page.locator('#manual-order-quantity')).toHaveValue('4');
  expect(api.orderRequests()).toBe(0);
  expect(errors).toEqual([]);
  await peer.close();
});
