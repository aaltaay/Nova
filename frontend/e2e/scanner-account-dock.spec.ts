import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { scannerOrdersDock } from './helpers/ordersDock';

test.describe('Scanner account dock', () => {
  test('sample scanner shows the Trader Positions strip', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');

    const desk = page.getByTestId('scanner-desk');
    await expect(desk).toBeVisible();
    const dock = scannerOrdersDock(page);
    await expect(dock).toBeVisible();
    await dock.getByTestId('stock-view-dock-tab-positions').click();
    await expect(dock.getByTestId('stock-view-positions')).toBeVisible();
    await expect(dock.getByTestId('positions-table')).toContainText('SMPL');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  // #357: the sample desk is a marketing surface and CI runs with no Nova API,
  // so both of these must hold without a backend.
  test('sample desk is badged and shows its own account figures', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');

    const badge = page.getByTestId('sample-data-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('Nova Marketing Sample Data');

    // The header must not contradict its own GATEWAY-connected chip.
    await expect(page.getByTestId('global-bar-cluster')).toBeVisible();
    await expect(page.getByTestId('global-bar-offline')).toHaveCount(0);
    await expect(page.getByTestId('global-bar-account-trigger')).toContainText('+$230.00');
    await expect(page.locator('.global-app-bar__metric--netliq')).toContainText('$100,000.00');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  // #357: Emergency KILL is a composite (bot L0 + desk lock + cancel-all +
  // flatten). On the sample desk it refuses as ONE unit. Guarding the
  // protective cancel while letting the destructive flatten through would
  // leave resting orders live on an account that was just market-flattened,
  // so the assertion that matters is that NO mutation leaves the browser.
  test('Emergency KILL on the sample desk fires no broker leg', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const mutations: string[] = [];
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const url = request.url();
      const method = request.method();
      const mutating =
        (method === 'DELETE' && url.includes('/api/ibkr/order'))
        || (method === 'POST' && url.includes('/api/ibkr/flatten-account'))
        || (method === 'POST' && url.includes('/api/ibkr/order'))
        || (method === 'PATCH' && url.includes('/bot/session'));
      if (mutating) mutations.push(`${method} ${url}`);
      await route.continue();
    });

    await page.goto('/?view=sample');
    await expect(page.getByTestId('sample-data-badge')).toBeVisible();

    await page.getByTestId('global-bar-emergency-kill').click();
    await page.getByTestId('app-dialog-confirm').click();

    const message = page.getByTestId('app-dialog-message');
    await expect(message).toContainText('Nova Marketing Sample Data');
    await expect(message).toContainText('nothing was cancelled or flattened');
    await expect(message).toContainText('Exit the sample desk');
    expect(mutations, `sample desk sent broker mutations:\n${mutations.join('\n')}`).toEqual([]);

    await page.getByTestId('app-dialog-ok').click();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
