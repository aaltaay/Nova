/**
 * Bot chrome after ADR 044: every view keeps the bar to desk chrome and the symbol-menu host.
 * The Trader rail carries no bot card: the strategies only watch (ADR 072).
 */
import { test, expect, type Page } from '@playwright/test';
import { clickThroughOverlay } from './helpers/accountReports';
import { attachErrorCollector } from './helpers/errorCollector';

const BAR_ARM_CONTROL_IDS = [
  'bot-arm-controls',
  'bot-arm-level',
  'bot-arm-allowlist',
  'bot-arm-allowlist-toggle',
  'bot-arm-status',
  'bots-activate',
] as const;

/** Row 1 is desk chrome on every view: account + trade lock on the right, never an arm control. */
async function expectDeskChromeOnRowOne(page: Page) {
  const right = page.locator('.global-app-bar__right');
  await expect(page.getByTestId('global-app-bar')).toBeVisible();
  await expect(page.getByTestId('global-bar-primary')).toBeVisible();
  await expect(right.getByTestId('bot-arm-controls')).toHaveCount(0);
  await expect(right.getByTestId('global-bar-account')).toBeVisible();
  await expect(right.getByTestId('global-bar-trade-lock')).toBeVisible();
}

/** Every view: the bar's bot row is only the symbol-menu host -- no arm control anywhere in the bar. */
async function expectBarHostOnly(page: Page) {
  await expectDeskChromeOnRowOne(page);
  const bar = page.getByTestId('global-app-bar');
  await expect(page.getByTestId('global-bar-bot')).toHaveCount(1);
  for (const id of BAR_ARM_CONTROL_IDS) {
    await expect(bar.getByTestId(id)).toHaveCount(0);
  }
}

test.describe('GlobalAppBar bot row', () => {
  test('sample scanner and TraderTV keep the bar to desk chrome; the rail has no Bots item (ADR 072)', async ({
    page,
  }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');
    await expectBarHostOnly(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-scanner.png'),
    });

    await expect(page.getByTestId('nav-rail-bots')).toHaveCount(0);
    const tradertv = page.getByTestId('nav-rail-tradertv');
    await clickThroughOverlay(page, tradertv);
    await expect(tradertv).toHaveClass(/is-active/);
    await expectBarHostOnly(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-tradertv.png'),
    });

    const gappers = page.getByTestId('nav-rail-tab-gappers');
    await clickThroughOverlay(page, gappers);
    await expect(gappers).toHaveClass(/is-active/);
    await expectBarHostOnly(page);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('sample trader keeps the bar to desk chrome, and its rail carries no bot card (ADR 072)', async ({
    page,
  }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page).toHaveTitle(/SMPL.*Trader/);
    await expectBarHostOnly(page);

    const rail = page.getByRole('complementary', { name: 'Trader' });
    await expect(rail).toBeVisible();
    await expect(page.getByTestId('bot-autonomy-card')).toHaveCount(0);
    await expect(page.locator('[data-testid^="bot-card-"]')).toHaveCount(0);

    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-trader.png'),
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
