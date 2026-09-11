import { expect, test, type Page, type Route } from '@playwright/test';
import { E2E_IBKR_STATUS } from './fixtures/orderRows';
import { attachErrorCollector } from './helpers/errorCollector';

async function emptyIbkrBars(route: Route) {
  const url = new URL(route.request().url());
  const timeframe = url.searchParams.get('timeframe') ?? '1Min';
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      symbol: 'SMPL',
      timeframe,
      bars: [],
      source: 'ibkr',
      coverage: {
        as_of: null,
        complete_through: null,
        filling: true,
      },
    }),
  });
}

async function mockFirstTapePrint(page: Page) {
  await page.routeWebSocket('**/ws/ibkr/tape/SMPL', (socket) => {
    setTimeout(() => {
      socket.send(JSON.stringify({
        type: 'subscribed',
        symbol: 'SMPL',
      }));
      socket.send(JSON.stringify({
        type: 'print',
        symbol: 'SMPL',
        time: '2026-09-11T13:29:55.000Z',
        price: 150,
        size: 100,
        exchange: 'ARCA',
        conditions: '',
        side: 'ask',
        bid: 149.99,
        ask: 150,
      }));
    }, 50);
  });
}

test('first live tape print removes the empty 10Sec loading overlay', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  await page.route('**/api/ibkr/status', (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(E2E_IBKR_STATUS),
    });
  });
  await page.route('**/api/ticker/SMPL/bars?*', emptyIbkrBars);
  await mockFirstTapePrint(page);

  await page.goto('/?view=sample&symbol=SMPL');

  const chart = page.getByTestId('ticker-chart-10Sec');
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute('data-bar-count', '1');
  await expect(chart.getByText('Loading IBKR historical...')).toHaveCount(0);
  expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
});
