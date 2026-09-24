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

/** First paint of the desk after `page.goto('/')`, cold dev server included. */
const FIRST_PAINT_TIMEOUT_MS = 30_000;

export async function clickThroughOverlay(page: Page, locator: Locator): Promise<void> {
  try {
    await locator.click({ timeout: 3000 });
  } catch {
    await dismissTradingPrereqIfOpen(page, 2000);
    // Same escape hatch as module-registry when a dock still sits on the hit box.
    await locator.evaluate((el: HTMLElement) => el.click());
  }
}

/**
 * Rail Account -> the Account page, past docks and the prereq overlay.
 * The page is the region named exactly "Account"; its left column is a
 * second region, "Account Details", so the name must not substring-match.
 */
export async function openAccountPage(page: Page): Promise<void> {
  const account = page.getByTestId('nav-rail-account');
  // The first spec of a run pays for Vite's cold compile of the whole desk,
  // which can take longer than the default 5 s on a loaded runner.
  await expect(account).toBeVisible({ timeout: FIRST_PAINT_TIMEOUT_MS });
  await dismissTradingPrereqIfOpen(page, 8000);
  await clickThroughOverlay(page, account);
  await expect(page.getByRole('region', { name: 'Account', exact: true })).toBeVisible();
  await dismissTradingPrereqIfOpen(page, 2000);
}

/**
 * The old Account module (Overview / Reports / Activity / Latency section
 * nav) is hosted under the page's Reports tab on every venue and under
 * Broker snapshot on Live only, so Reports is the door that always exists.
 */
export async function openHostedAccountModule(page: Page): Promise<void> {
  const reportsTab = page.getByTestId('account-page-tab-reports');
  await expect(reportsTab).toBeVisible();
  await clickThroughOverlay(page, reportsTab);
  await expect(page.getByTestId('account-section-reports')).toBeVisible();
}

/** Rail Account -> Reports tab -> Activity section, past docks and the prereq overlay. */
export async function openAccountActivity(page: Page): Promise<void> {
  await openAccountPage(page);
  await openHostedAccountModule(page);
  const activity = page.getByTestId('account-section-activity');
  await expect(activity).toBeVisible();
  await clickThroughOverlay(page, activity);
  await expect(page.getByTestId('activity-trail')).toBeVisible();
}

/** Rail Account -> Reports tab (the Reports section is its initial section). */
export async function openAccountReports(page: Page): Promise<void> {
  await openAccountPage(page);
  await openHostedAccountModule(page);
  await expect(page.getByTestId('account-section-reports')).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByTestId('reports-import')).toBeVisible();
}
