import { test, expect, type Page } from '@playwright/test';
import { mockPhoneApi, phoneOverflow } from './helpers/phoneApi';

// When the PC stops answering (ADR 070; desk-ops.md "When the PC stops answering"): the phone says why,
// how old the screen is and what to do, on every screen, without scrolling. Nothing here reaches a real backend.
const PORTRAIT = { width: 360, height: 720 };
const LANDSCAPE = { width: 740, height: 320 };

test.use({ viewport: PORTRAIT, hasTouch: true });

async function open(page: Page, hash: string) {
  await page.goto(`/phone.html#/${hash}`);
}

test('a PC that stops answering puts up the sheet after 5 s, and a good answer takes it down', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await open(page, 'home');
  await expect(page.getByTestId('phone-link')).toHaveAttribute('data-tone', 'good');
  await expect(page.getByTestId('phone-nolink')).toHaveCount(0);
  await expect(page.getByTestId('phone-stale')).toHaveCount(0);

  api.state.linkDown = 'gone';
  const sheet = page.getByTestId('phone-nolink');
  await expect(sheet).toBeVisible({ timeout: 15_000 });
  await expect(sheet).toHaveAttribute('data-kind', 'pc');
  await expect(sheet).toContainText("Can't reach your PC");
  await expect(sheet).toContainText('Last answer');
  await expect(sheet).toContainText('Turn Tailscale on, on this phone.');
  await expect(sheet).toContainText('Nothing can be sent until the link is back.');
  await expect(page.getByTestId('phone-stale')).toContainText('Not live.');
  expect(await phoneOverflow(page)).toEqual([]);

  // The X closes the sheet; the amber line stays, and the red pill opens the sheet again.
  await page.getByTestId('phone-nolink-close').click();
  await expect(sheet).toHaveCount(0);
  await expect(page.getByTestId('phone-stale')).toBeVisible();
  await page.getByTestId('phone-link').click();
  await expect(sheet).toBeVisible();

  // The tunnel answers but Nova does not: a different cause, a different fix, no Tailscale button.
  api.state.linkDown = 502;
  await expect(sheet).toHaveAttribute('data-kind', 'nova-down', { timeout: 15_000 });
  await expect(sheet).toContainText("Nova isn't running on the PC");
  await expect(page.getByTestId('phone-nolink-tailscale')).toHaveCount(0);
  expect(await phoneOverflow(page)).toEqual([]);

  api.state.linkDown = undefined;
  await page.getByTestId('phone-nolink-retry').click();
  await expect(sheet).toHaveCount(0);
  await expect(page.getByTestId('phone-stale')).toHaveCount(0);
  await expect(page.getByTestId('phone-link')).toHaveAttribute('data-tone', 'good');
});

test('the sheet fits the Trade screen upright and the big chart on its side', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await open(page, 'trade/ABCD');
  await expect(page.getByTestId('phone-buy-market')).toBeVisible();
  api.state.linkDown = 'gone';
  await expect(page.getByTestId('phone-nolink')).toBeVisible({ timeout: 15_000 });
  expect(await phoneOverflow(page)).toEqual([]);
  // Trade has no link pill: its Data / Tap pill says No link, and opens the sheet again.
  await page.getByTestId('phone-nolink-close').click();
  await expect(page.getByTestId('phone-nolink')).toHaveCount(0);
  await expect(page.getByTestId('phone-fresh')).toContainText('No link');
  await page.getByTestId('phone-fresh').click();
  await expect(page.getByTestId('phone-nolink')).toBeVisible();

  await page.setViewportSize(LANDSCAPE);
  await open(page, 'chart/ABCD');
  await expect(page.getByTestId('phone-nolink')).toBeVisible({ timeout: 15_000 });
  expect(await phoneOverflow(page)).toEqual([]);
});
