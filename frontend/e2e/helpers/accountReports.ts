import { expect, type Locator, type Page } from '@playwright/test';

/**
 * CI runs without Nova API. After a few failed health probes the
 * Trading prerequisites overlay covers the desk (fixed, z-index 9000).
 * Close it the way an operator does -- the checklist is not a desk block.
 */
export async function dismissTradingPrereqIfOpen(
  page: Page,
  timeoutMs = 4000,
): Promise<void> {
  const gate = page.getByTestId('trading-prerequisites-gate');
  const close = page.getByTestId('trading-prereq-close');
  try {
    await gate.waitFor({ state: 'visible', timeout: timeoutMs });
  } catch {
    return;
  }
  await close.click();
  await expect(gate).toHaveCount(0);
}

async function clickThroughOverlay(page: Page, locator: Locator): Promise<void> {
  try {
    await locator.click({ timeout: 3000 });
  } catch {
    await dismissTradingPrereqIfOpen(page, 2000);
    // Same escape hatch as module-registry when a dock still sits on the hit box.
    await locator.evaluate((el: HTMLElement) => el.click());
  }
}

/** Account header -> Activity section, past docks and the prereq overlay. */
export async function openAccountActivity(page: Page): Promise<void> {
  const account = page.getByTestId('global-bar-account-nav');
  await expect(account).toBeVisible();
  await dismissTradingPrereqIfOpen(page, 8000);
  await clickThroughOverlay(page, account);
  await expect(page.getByRole('region', { name: 'Account' })).toBeVisible();
  await dismissTradingPrereqIfOpen(page, 2000);
  const activity = page.getByTestId('account-section-activity');
  await expect(activity).toBeVisible();
  await clickThroughOverlay(page, activity);
  await expect(page.getByTestId('activity-trail')).toBeVisible();
}

/** Account header -> Reports section, past docks and the prereq overlay. */
export async function openAccountReports(page: Page): Promise<void> {
  const account = page.getByTestId('global-bar-account-nav');
  await expect(account).toBeVisible();
  await dismissTradingPrereqIfOpen(page, 8000);
  await clickThroughOverlay(page, account);
  await expect(page.getByRole('region', { name: 'Account' })).toBeVisible();
  await dismissTradingPrereqIfOpen(page, 2000);
  const reports = page.getByTestId('account-section-reports');
  await expect(reports).toBeVisible();
  await clickThroughOverlay(page, reports);
  await expect(page.getByTestId('reports-import')).toBeVisible();
}
