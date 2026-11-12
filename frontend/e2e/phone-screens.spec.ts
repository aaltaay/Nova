import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { PHONE_PIN, mockPhoneApi, phoneOverflow } from './helpers/phoneApi';

// Nova on the phone (ADR 070): every screen against a stand-in API. Nothing here reaches a real backend.
const PORTRAIT = { width: 360, height: 720 };
const LANDSCAPE = { width: 740, height: 320 };

test.use({ viewport: PORTRAIT, hasTouch: true });

async function open(page: Page, hash: string) {
  await page.goto(`/phone.html#/${hash}`);
}

const SCREENS: readonly { hash: string; name: string; ready: string }[] = [
  { hash: 'home', name: 'home', ready: 'phone-day-read' },
  { hash: 'scan', name: 'scan', ready: 'phone-scan-row-ABCD' },
  { hash: 'top9', name: 'top9', ready: 'phone-top9-grid' },
  { hash: 'account', name: 'account', ready: 'phone-position-ABCD' },
  { hash: 'settings', name: 'settings', ready: 'phone-settings-link' },
  { hash: 'stock/ABCD', name: 'stock', ready: 'phone-stock-quote' },
  { hash: 'trade/ABCD', name: 'trade', ready: 'phone-trade-soon' },
];

for (const screen of SCREENS) {
  test(`${screen.name} fits the phone: nothing scrolls, nothing is cut off, nothing is written`, async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const api = await mockPhoneApi(page);
    await open(page, screen.hash);
    await expect(page.getByTestId(`phone-screen-${screen.name}`)).toBeVisible();
    await expect(page.getByTestId(screen.ready)).toBeVisible();
    // Settings shows the venue as its three tiles; every other screen carries the pill.
    if (screen.name !== 'settings') await expect(page.getByTestId('phone-venue')).toHaveText('PAPER');
    await expect(page.getByTestId('phone-link').first()).toHaveAttribute('data-tone', 'good');
    expect(await phoneOverflow(page)).toEqual([]);
    // A screen that only reads sends no write at all, and asks for nothing the stand-in does not know.
    expect(api.writes).toEqual([]);
    expect(api.unanswered.filter((p) => !p.startsWith('/api/luld/'))).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test('the big chart is drawn for a phone on its side, and says to turn an upright one', async ({ page }) => {
  await mockPhoneApi(page);
  await open(page, 'chart/ABCD');
  await expect(page.getByText('Turn your phone sideways')).toBeVisible();
  await page.setViewportSize(LANDSCAPE);
  await expect(page.getByTestId('phone-chart')).toBeVisible();
  await expect(page.getByTestId('ticker-chart-1Min')).toHaveAttribute('data-bar-count', /^[1-9]/);
  expect(await phoneOverflow(page)).toEqual([]);
  // The layers the desk chart can switch are switches; the rest say why they are not.
  await page.getByRole('button', { name: /^Indicators/ }).click();
  const layers = page.getByTestId('phone-chart-layers');
  await expect(layers.getByRole('menuitemcheckbox', { name: 'MACD' })).toBeEnabled();
  await expect(layers.getByRole('menuitemcheckbox', { name: 'Levels' })).toBeDisabled();
  expect(await phoneOverflow(page)).toEqual([]);
});

test('a viewport smaller than the drawing shrinks the whole page instead of scrolling', async ({ page }) => {
  await mockPhoneApi(page);
  await page.setViewportSize({ width: 360, height: 600 });
  await open(page, 'scan');
  await expect(page.getByTestId('phone-scan-row-ABCD')).toBeVisible();
  expect(await phoneOverflow(page)).toEqual([]);
  const zoom = await page.locator('.ph-root').evaluate((el) => Number(getComputedStyle(el).zoom));
  expect(zoom).toBeCloseTo(600 / 720, 2);
});

test('Scan pages a long list, and a row and its chip lead to different screens', async ({ page }) => {
  await mockPhoneApi(page);
  await open(page, 'scan');
  const list = page.getByTestId('phone-scan-rows');
  await expect(list.locator('.ph-scan__row')).toHaveCount(12);
  await expect(page.getByTestId('phone-scan-count')).toHaveText('1 to 12 of 34');
  await page.getByRole('button', { name: 'Next ›' }).click();
  await expect(page.getByTestId('phone-scan-count')).toHaveText('13 to 24 of 34');
  // The second page carries on from 13: a row's number is its place on the whole list.
  await expect(list.locator('.ph-scan__rank').first()).toHaveText('13');
  await page.getByRole('button', { name: '‹ Prev' }).click();
  await expect(page.getByTestId('phone-scan-row-ABCD').locator('.ph-scan__rank')).toHaveText('1');
  await expect(page.getByTestId('phone-scan-row-WXYZ').locator('.ph-scan__rank')).toHaveText('2');
  // A filter hides rows and leaves the numbers of the rest alone: only the halted row (number 3) stays.
  await page.getByTestId('phone-scan-filter').click();
  await page.getByRole('menuitemcheckbox', { name: 'Halted' }).click();
  await expect(list.locator('.ph-scan__row')).toHaveCount(1);
  await expect(page.getByTestId('phone-scan-row-QRST').locator('.ph-scan__rank')).toHaveText('3');
  await expect(page.getByTestId('phone-scan-count')).toContainText('33 hidden');
  await page.getByRole('menuitemcheckbox', { name: 'Halted' }).click();
  await page.getByTestId('phone-scan-filter').click();
  await expect(list.locator('.ph-scan__row')).toHaveCount(12);

  // The halted row says so, in the place the news goes.
  await expect(page.getByTestId('phone-scan-row-QRST')).toContainText('Halted');
  // The row whose news the scanner classified names it, with its age.
  await expect(page.getByTestId('phone-scan-row-ABCD')).toContainText('News');
  await expect(page.getByTestId('phone-scan-row-ABCD')).toContainText('9m ago');

  await page.getByTestId('phone-chip-WXYZ').click();
  await expect(page).toHaveURL(/#\/trade\/WXYZ$/);
  await page.goBack();
  await page.getByRole('button', { name: "Open WXYZ's stock page" }).click();
  await expect(page).toHaveURL(/#\/stock\/WXYZ$/);
  await expect(page.getByTestId('phone-stock-quote')).toContainText('4.82');
});

test('a Scan list that is not on the phone yet is locked and says why', async ({ page }) => {
  await mockPhoneApi(page);
  await open(page, 'scan');
  await page.getByTestId('phone-scan-more').click();
  const hod = page.getByRole('menuitemradio', { name: 'HOD Momo' });
  await expect(hod).toBeDisabled();
  await expect(hod).toHaveAttribute('data-why', /Not on the phone yet/);
  await page.getByRole('menuitemradio', { name: 'Large Cap' }).click();
  await expect(page.getByTestId('phone-scan-count')).toHaveText('1 to 5 of 5');
  expect(await phoneOverflow(page)).toEqual([]);
});

test('the padlock asks for the phone PIN, refuses a wrong one in the door\'s words, and opens on the right one', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await open(page, 'settings');
  await expect(page.getByTestId('phone-settings-phone')).toContainText('This phone is locked');
  await page.getByTestId('phone-settings-padlock').getByRole('button', { name: 'Unlock' }).click();
  const sheet = page.getByTestId('phone-pin-sheet');
  await expect(sheet).toBeVisible();
  expect(await phoneOverflow(page)).toEqual([]);
  for (const digit of '111111') await sheet.getByRole('button', { name: digit, exact: true }).click();
  await expect(sheet).toContainText('That is not the phone PIN.');
  expect(api.state.armed).toBe(false);

  for (const digit of PHONE_PIN) await sheet.getByRole('button', { name: digit, exact: true }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByTestId('phone-banner')).toContainText("Paper's padlock is open.");
  await expect(page.getByTestId('phone-settings-padlock')).toContainText('Padlock open');
  await expect(page.getByTestId('phone-settings-phone')).toContainText('This phone is unlocked');
  await expect(page.getByTestId('phone-settings-phone')).toContainText('7 h');
  expect(api.state.armed).toBe(true);
  // Every write went through the phone's own door.
  expect(api.writes).toEqual(['POST /api/phone/unlock', 'POST /api/phone/unlock', 'POST /api/phone/arm']);

  await page.getByTestId('phone-settings-phone').getByRole('button', { name: 'Lock' }).click();
  await expect(page.getByTestId('phone-settings-phone')).toContainText('This phone is locked');
});

test('Home cancels a working order through the door and says what the desk answered', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await open(page, 'home');
  const holdings = page.getByTestId('phone-holdings');
  await expect(holdings).toContainText('Working');
  await holdings.getByRole('button', { name: 'Cancel' }).click();
  const sheet = page.getByTestId('phone-pin-sheet');
  for (const digit of PHONE_PIN) await sheet.getByRole('button', { name: digit, exact: true }).click();
  await expect(page.getByTestId('phone-banner')).toContainText('Cancelled: ABCD Sell 250 at 4.95.');
  await expect(holdings).not.toContainText('Working');
  expect(api.writes).toEqual(['POST /api/phone/unlock', 'DELETE /api/phone/order/7']);
});

test('a desk that is not on Paper is shown as it is, and the phone will not open its padlock', async ({ page }) => {
  await mockPhoneApi(page, { venue: 'sim' });
  await open(page, 'settings');
  await expect(page.getByTestId('phone-settings-venues').locator('[aria-pressed="true"]')).toHaveAttribute('data-venue', 'sim');
  const unlock = page.getByTestId('phone-settings-padlock').getByRole('button', { name: 'Unlock' });
  await expect(unlock).toBeDisabled();
  await expect(unlock).toHaveAttribute('data-why', /Paper only/);
});

test('when the account stops answering, the last rows stay and the screen says they are not current', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await open(page, 'account');
  await expect(page.getByTestId('phone-position-ABCD')).toBeVisible();
  await expect(page.getByTestId('phone-account-error')).toHaveCount(0);
  api.state.accountDown = true;
  await expect(page.getByTestId('phone-account-error')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('phone-position-ABCD')).toBeVisible();
  expect(await phoneOverflow(page)).toEqual([]);

  await page.getByRole('button', { name: 'Home' }).click();
  await expect(page.getByTestId('phone-holdings-error')).toBeVisible();
  await expect(page.getByTestId('phone-holdings')).toContainText('ABCD');
  expect(await phoneOverflow(page)).toEqual([]);
});

test('a session that ended asks for the PIN on the next tap instead of sending a write that is refused', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await open(page, 'home');
  const holdings = page.getByTestId('phone-holdings');
  await holdings.getByRole('button', { name: 'Cancel' }).click();
  const sheet = page.getByTestId('phone-pin-sheet');
  for (const digit of PHONE_PIN) await sheet.getByRole('button', { name: digit, exact: true }).click();
  await expect(holdings).not.toContainText('Working');
  // The backend restarts: the session is gone, and a new order is working.
  api.state.unlocked = false;
  api.state.working = [9];
  api.writes.length = 0;
  await expect(holdings).toContainText('Working', { timeout: 15_000 });
  await page.waitForTimeout(1_500);
  await holdings.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet).toBeVisible();
  // Nothing was sent before the PIN was asked for.
  expect(api.writes).toEqual([]);
});
