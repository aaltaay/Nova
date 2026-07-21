/**
 * L3 Orders pyramid — Stock View Open/Closed dock with mocked IBKR APIs.
 * Never places/cancels real orders (tester safety).
 */
import { test, expect, type ConsoleMessage, type Page, type Route } from '@playwright/test';
import {
  E2E_ACCOUNT,
  E2E_CLOSED_API_CANCELLED,
  E2E_CLOSED_FILLED,
  E2E_CLOSED_INACTIVE,
  E2E_CLOSED_PARTIAL_CANCEL,
  E2E_IBKR_STATUS,
  E2E_POSITION_AAPL,
  E2E_WORKING_API_PENDING,
  E2E_WORKING_PARTIAL,
  E2E_WORKING_PRESUBMITTED,
} from './fixtures/orderRows';

function attachErrorCollector(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on('pageerror', (err) => {
    errors.push(`pageerror: ${err.message}`);
  });
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (/Failed to load resource|net::ERR_|WebSocket/i.test(text)) return;
    errors.push(`console.error: ${text}`);
  });
  return { errors };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockIbkrOrderApis(page: Page) {
  const closedPayload = [
    E2E_CLOSED_FILLED,
    E2E_CLOSED_PARTIAL_CANCEL,
    E2E_CLOSED_API_CANCELLED,
    E2E_CLOSED_INACTIVE,
  ];
  await page.route('**/api/ibkr/orders/closed**', (route) =>
    json(route, closedPayload),
  );
  await page.route('**/api/ibkr/orders**', async (route) => {
    const url = route.request().url();
    if (url.includes('/orders/closed')) {
      await json(route, closedPayload);
      return;
    }
    await json(route, [
      E2E_WORKING_PARTIAL,
      E2E_WORKING_PRESUBMITTED,
      E2E_WORKING_API_PENDING,
    ]);
  });
  // Place / cancel — hard ban (POST /api/ibkr/order, DELETE /api/ibkr/order/:id)
  await page.route('**/api/ibkr/order', async (route) => {
    if (route.request().method() === 'GET') {
      await route.continue();
      return;
    }
    await json(
      route,
      { ok: false, error: 'e2e hard-ban: no place/cancel in open-closed-orders.spec' },
      403,
    );
  });
  await page.route('**/api/ibkr/order/**', async (route) => {
    await json(
      route,
      { ok: false, error: 'e2e hard-ban: no place/cancel in open-closed-orders.spec' },
      403,
    );
  });

  await page.route('**/api/ibkr/status', (route) => json(route, E2E_IBKR_STATUS));
  await page.route('**/api/ibkr/account', (route) => json(route, E2E_ACCOUNT));
  await page.route('**/api/ibkr/positions', (route) =>
    json(route, [E2E_POSITION_AAPL]),
  );
}

test.describe('Orders pyramid L3 — Open/Closed dock (mocked API)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      try {
        localStorage.setItem('nova.stockView.openOrders.collapsed', '0');
        localStorage.removeItem('nova.stockView.openOrders.sampleHidden');
        localStorage.setItem('nova.stockView.dock.surface', 'orders');
        localStorage.setItem('nova.stockView.ordersToday.filter', 'working');
      } catch {
        /* ignore */
      }
    });
    await mockIbkrOrderApis(page);
  });

  test('Open Orders shows filled, remaining, limit, avg, id, submitted time', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    await expect(page.getByTestId('stock-view-open-orders-dock')).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByTestId('stock-view-working-orders')).toBeVisible();
    const panel = page.getByTestId('working-orders-panel');
    await expect(panel).toBeVisible();

    const text = await panel.innerText();
    expect(text).toContain('40');
    expect(text).toContain('60');
    expect(text).toContain('$190.55');
    expect(text).toContain('$190.42');
    expect(text).toContain('4242');
    expect(text).toContain('Pending'); // PreSubmitted + ApiPending
    // Submitted 09:41:23 ET — not updated_at 14:00 ET
    expect(text).toMatch(/09:41:23/);
    expect(text).not.toMatch(/14:00:00/);

    const fillBtn = page.getByRole('button', { name: /Fill now order 4242/i });
    await expect(fillBtn).toBeEnabled();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Closed Orders shows filled, partial cancel, ApiCancelled, Failed', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    await page.getByTestId('orders-today-filter-all').click();
    await expect(page.getByTestId('orders-today-view')).toBeVisible();
    await page.getByTestId('orders-today-filter-filled').click();
    await expect(page.getByTestId('stock-view-closed-orders')).toBeVisible({
      timeout: 15_000,
    });
    // Partial cancel + Failed live under other segments — use All for full matrix.
    await page.getByTestId('orders-today-filter-all').click();
    const closed = page.getByTestId('stock-view-closed-orders');
    await expect(closed).toBeVisible();

    const text = await closed.innerText();
    expect(text).toContain('9001');
    expect(text).toContain('$12.48');
    expect(text).toContain('9004');
    expect(text).toContain('35');
    expect(text).toContain('9006');
    expect(text).toContain('9007');
    expect(text).toMatch(/Cancelled \(partial fill\)/);
    expect(text).toContain('Failed'); // Inactive
    // Activity time for filled row (09:41:23 ET from updated_at)
    expect(text).toMatch(/09:41:23/);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Positions dock shows open holdings from IBKR account', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    await expect(page.getByTestId('stock-view-open-orders-dock')).toBeVisible({
      timeout: 20_000,
    });
    await page.getByTestId('stock-view-dock-tab-positions').click();
    await expect(page.getByTestId('stock-view-positions')).toBeVisible();
    const table = page.getByTestId('positions-table');
    await expect(table).toBeVisible();
    const text = await table.innerText();
    expect(text).toContain('AAPL');
    expect(text).toContain('100');
    expect(text).toMatch(/190\.00|190/);
    expect(text).toMatch(/191\.20|191\.2/);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
