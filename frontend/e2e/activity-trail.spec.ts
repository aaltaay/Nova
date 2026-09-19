/**
 * Account > Activity trail -- mocked journal/ledger join, no live IBKR.
 */
import { expect, test, type Page, type Route } from '@playwright/test';
import { openAccountActivity } from './helpers/accountReports';
import { attachErrorCollector } from './helpers/errorCollector';

const TRAIL = {
  count: 1,
  includes_mock_data: false,
  items: [
    {
      id: 'trade:1',
      kind: 'closed',
      trade_id: 1,
      symbol: 'IVF',
      side: 'long',
      qty: 10,
      entry_price: 5,
      exit_price: 6.5,
      pnl: 12.75,
      commission: 2.25,
      pnl_basis: 'net',
      opened_ts: 1_700_000_000,
      closed_ts: 1_700_000_100,
      close_key: 'IVF|buy|flat',
      notes: 'Nova round trip buy -> flat; net of CommissionReport $2.25',
      events: [
        { kind: 'place', ts: 1_700_000_000, side: 'BUY', qty: 10 },
        { kind: 'fill', ts: 1_700_000_010, side: 'BUY', qty: 10, price: 5 },
        { kind: 'flatten', ts: 1_700_000_080, side: 'SELL', qty: 10 },
        { kind: 'fill', ts: 1_700_000_090, side: 'SELL', qty: 10, price: 6.5 },
        { kind: 'commission', ts: 1_700_000_090, commission: 1.25 },
        { kind: 'close', ts: 1_700_000_100, pnl: 12.75, commission: 2.25 },
      ],
    },
  ],
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockActivityApis(page: Page) {
  await page.route('**/api/journal/trail**', route => json(route, TRAIL));
  await page.route('**/api/ibkr/executions**', route => json(route, []));
  await page.route('**/api/ibkr/gateway-trail**', route => json(route, { events: [] }));
}

test('Account Activity trail shows place-fill-flatten-close', async ({ page }) => {
  attachErrorCollector(page);
  await mockActivityApis(page);
  await page.goto('/');
  await openAccountActivity(page);
  const trail = page.getByTestId('activity-trail');
  await expect(trail).toContainText('IVF');
  await expect(trail).toContainText('$12.75');
  await expect(trail).toContainText('$2.25');
  await expect(trail).toContainText('Place -> Fill -> Flatten -> Fill -> Commission -> Close');
  await page.getByTestId('activity-trail-row-trade:1').click();
  await expect(page.getByTestId('activity-trail-detail-trade:1')).toBeVisible();
  await expect(page.getByTestId('activity-trail-detail-trade:1')).toContainText('Flatten');
});
