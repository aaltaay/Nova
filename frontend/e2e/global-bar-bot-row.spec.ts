/**
 * Bot Autonomy chrome after ADR 027 (2026-09-23): the bar never carries arm
 * controls -- the Bots page hero owns the level and Activate, the Trader
 * carries them in its right-rail Bot Autonomy card (Level / Setup /
 * Allowlist / Activate), and every view keeps the bar to desk chrome and the
 * symbol-menu host.
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

const CARD_CONTROL_IDS = [
  'bot-card-level',
  'bot-card-setup',
  'bot-card-setup-info',
  'bot-arm-allowlist',
  'bot-arm-allowlist-toggle',
  'bot-card-state',
  'bot-card-activate',
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
  test('sample scanner and the Bots page keep the bar to desk chrome -- the hero owns the level', async ({
    page,
  }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');
    await expectBarHostOnly(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-scanner.png'),
    });

    const bots = page.getByTestId('nav-rail-bots');
    await clickThroughOverlay(page, bots);
    await expect(bots).toHaveClass(/is-active/);
    await expectBarHostOnly(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-bots.png'),
    });

    const gappers = page.getByTestId('nav-rail-tab-gappers');
    await clickThroughOverlay(page, gappers);
    await expect(gappers).toHaveClass(/is-active/);
    await expectBarHostOnly(page);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('sample trader window carries the bot controls in the rail Bot Autonomy card, not the bar', async ({
    page,
  }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page).toHaveTitle(/SMPL.*Trader/);
    await expectBarHostOnly(page);

    const rail = page.getByRole('complementary', { name: 'Trader' });
    const card = rail.getByTestId('bot-autonomy-card');
    await expect(card).toBeVisible();
    for (const id of CARD_CONTROL_IDS) {
      await expect(card.getByTestId(id)).toBeVisible();
    }
    await expect(page.getByTestId('bot-autonomy-card')).toHaveCount(1);

    // The card sits in the rail under the bar, never over the page.
    const barBox = await page.getByTestId('global-app-bar').boundingBox();
    const cardBox = await card.boundingBox();
    expect(barBox).toBeTruthy();
    expect(cardBox).toBeTruthy();
    expect(cardBox!.y).toBeGreaterThanOrEqual(barBox!.y + barBox!.height);

    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-trader.png'),
    });
    await card.screenshot({
      path: testInfo.outputPath('bot-autonomy-card-sample-trader.png'),
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
