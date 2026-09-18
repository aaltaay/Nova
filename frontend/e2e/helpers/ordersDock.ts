import type { Locator, Page } from '@playwright/test';

/** Active Trader Orders dock -- never the keep-alive / scanner instance. */
export function traderOrdersDock(page: Page, symbol = 'AAPL'): Locator {
  return page.locator(`[data-dock-host="trader"][data-dock-symbol="${symbol}"]`);
}

/** Scanner account strip -- only while Dashboard is mounted. */
export function scannerOrdersDock(page: Page): Locator {
  return page.getByTestId('scanner-desk').locator('[data-dock-host="scanner"]');
}
