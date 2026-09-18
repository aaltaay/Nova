import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

async function expectBotRowBelowPrimary(page: import('@playwright/test').Page) {
  const primary = page.getByTestId('global-bar-primary');
  const bot = page.getByTestId('global-bar-bot');
  const right = page.locator('.global-app-bar__right');
  await expect(page.getByTestId('global-app-bar')).toBeVisible();
  await expect(primary).toBeVisible();
  await expect(bot).toBeVisible();
  await expect(bot.getByTestId('bot-arm-controls')).toBeVisible();
  await expect(bot.getByTestId('bot-arm-level')).toBeVisible();
  await expect(bot.getByTestId('bot-arm-pack')).toBeVisible();
  await expect(bot.getByTestId('bot-arm-pack-desc')).toBeVisible();
  await expect(bot.getByTestId('bot-arm-allowlist')).toBeVisible();
  await expect(bot.getByTestId('bot-arm-allowlist-toggle')).toBeVisible();
  await expect(bot.getByTestId('bot-arm-status')).toBeVisible();
  await expect(right.getByTestId('bot-arm-controls')).toHaveCount(0);
  await expect(right.getByTestId('global-bar-account')).toBeVisible();
  await expect(right.getByTestId('global-bar-trade-lock')).toBeVisible();
  const primaryBox = await primary.boundingBox();
  const botBox = await bot.boundingBox();
  expect(primaryBox).toBeTruthy();
  expect(botBox).toBeTruthy();
  expect(botBox!.y).toBeGreaterThan(primaryBox!.y);
}

test.describe('GlobalAppBar bot row', () => {
  test('sample scanner keeps desk chrome on row 1 and bot controls on row 2', async ({
    page,
  }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');
    await expectBotRowBelowPrimary(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-scanner.png'),
    });

    await page.setViewportSize({ width: 900, height: 720 });
    await expectBotRowBelowPrimary(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-scanner-narrow.png'),
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('sample trader window uses the same second bot row', async ({ page }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page).toHaveTitle(/SMPL.*Trader/);
    await expectBotRowBelowPrimary(page);
    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-app-bar-sample-trader.png'),
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
