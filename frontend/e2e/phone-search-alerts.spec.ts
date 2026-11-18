import { test, expect, type Page, type TestInfo } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { PHONE_PIN, mockPhoneApi, phoneOverflow } from './helpers/phoneApi';
import { NOTIFY_DEFAULTS, SAMPLE_ENDPOINT, fakePush } from './helpers/phoneNotifyApi';

// The phone's Search, its HOD Momo list and its Notifications (ADR 070, amendment 2026-11-18; mockup v1),
// against the stand-in API. Nothing here reaches a real backend or a real push service.
const PORTRAIT = { width: 360, height: 720 };
/** What is left of the screen above the phone's keyboard. */
const KEYBOARD_UP = { width: 360, height: 430 };

test.use({ viewport: PORTRAIT, hasTouch: true });

async function open(page: Page, hash: string) {
  await page.goto(`/phone.html#/${hash}`);
}

async function shot(page: Page, info: TestInfo, name: string) {
  await page.screenshot({ path: info.outputPath(`${name}.png`) });
}

async function typePin(page: Page) {
  await expect(page.getByTestId('phone-pin-sheet')).toBeVisible();
  for (const digit of PHONE_PIN) await page.getByTestId('phone-pin-sheet').getByRole('button', { name: digit, exact: true }).click();
  await expect(page.getByTestId('phone-pin-sheet')).toHaveCount(0);
}

test('search opens from Scan, fits above the keyboard, and finds a stock by ticker or company', async ({ page }, info) => {
  const { errors } = attachErrorCollector(page);
  const api = await mockPhoneApi(page);
  await open(page, 'scan');
  await expect(page.getByTestId('phone-scan-row-ABCD')).toBeVisible();
  expect(await phoneOverflow(page)).toEqual([]);

  await page.getByTestId('phone-scan-search').click();
  await expect(page.getByTestId('phone-screen-search')).toBeVisible();
  await expect(page).toHaveURL(/#\/search$/);
  const input = page.getByTestId('phone-search-input');
  await expect(input).toBeFocused();
  // Nothing typed, nothing looked up before: today's hot list.
  await expect(page.getByText("Today's hot list")).toBeVisible();
  await expect(page.getByTestId('phone-search-row-ABCD')).toContainText('Sample Alpha Holdings Inc.');
  await expect(page.getByTestId('phone-search-row-ABCD')).not.toContainText('Ordinary Shares');
  expect(await phoneOverflow(page)).toEqual([]);

  // The keyboard takes the lower part of the screen: the page is not shrunk, and the rows that fit are shown.
  await page.setViewportSize(KEYBOARD_UP);
  await input.fill('ab');
  await expect(input).toHaveValue('AB');
  await expect(page.getByTestId('phone-search-row-ABCD')).toBeVisible();
  await expect(page.getByTestId('phone-search-row-ABCD')).toContainText('Gappers #1');
  await expect(page.getByTestId('phone-search-row-ABCE')).toContainText('not on a board');
  await expect(page.getByTestId('phone-search-foot')).toContainText(/of 10 matches · keep typing to narrow/);
  expect(await page.evaluate(() => (document.querySelector('.ph-root') as HTMLElement).style.zoom)).toBe('1');
  expect(await phoneOverflow(page)).toEqual([]);
  await shot(page, info, '2-search-typing');

  // A company name finds its ticker.
  await input.fill('zebra');
  await expect(page.getByTestId('phone-search-row-ZEBR')).toContainText('Sample Zebra Aerospace Inc.');
  await expect(page.getByTestId('phone-search-foot')).toHaveText('1 match');
  // The keyboard's Go opens the first row in the Trader.
  await input.press('Enter');
  await expect(page).toHaveURL(/#\/trade\/ZEBR$/);

  // Back on Search with nothing typed, the stock just opened is first under Recent.
  await page.setViewportSize(PORTRAIT);
  await open(page, 'search');
  await expect(page.getByText('Recent', { exact: true })).toBeVisible();
  await expect(page.locator('.ph-find__row').first()).toHaveAttribute('data-testid', 'phone-search-row-ZEBR');
  expect(await phoneOverflow(page)).toEqual([]);
  await shot(page, info, '1-search-empty');
  // A row opens the stock page; its chip opens the Trader.
  await page.getByTestId('phone-search-row-ABCD').getByRole('button', { name: "Open ABCD's stock page" }).click();
  await expect(page).toHaveURL(/#\/stock\/ABCD$/);
  await open(page, 'search');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByTestId('phone-screen-scan')).toBeVisible();

  expect(api.writes).toEqual([]);
  expect(api.unanswered.filter((p) => !p.startsWith('/api/luld/'))).toEqual([]);
  expect(errors).toEqual([]);
});

test('HOD Momo and Running Up open under More: one row per stock, paged, nothing written', async ({ page }, info) => {
  const { errors } = attachErrorCollector(page);
  const api = await mockPhoneApi(page);
  await open(page, 'scan');
  await page.getByTestId('phone-scan-more').click();
  await page.getByRole('menuitemradio', { name: 'HOD Momo' }).click();
  const list = page.getByTestId('phone-hod-hod_momo');
  await expect(list).toBeVisible();
  // ABCD alerted twice on this list (and once on Running Up, which is not counted here): one row, at its first catch.
  await expect(page.getByTestId('phone-hod-row-ABCD')).toContainText('×2');
  await expect(page.getByTestId('phone-hod-row-ABCD')).toContainText('Up 10% / 10m');
  await expect(page.getByTestId('phone-hod-row-QRST')).toContainText('Near the high');
  await expect(list).toContainText('14 stocks today · newest first');
  // Fourteen stocks do not fit: the list pages, and nothing scrolls.
  await expect(page.getByTestId('phone-hod-count')).toHaveText(/^1 to \d+ of 14$/);
  await expect(page.getByTestId('phone-hod-notify')).toContainText(/Notifications (Off|Blocked)/);
  expect(await phoneOverflow(page)).toEqual([]);
  await shot(page, info, '3-scan-hod-momo');
  await list.getByRole('button', { name: 'Next ›' }).click();
  await expect(page.getByTestId('phone-hod-count')).toHaveText(/ to 14 of 14$/);
  expect(await phoneOverflow(page)).toEqual([]);

  // The list is remembered, as every Scan list is.
  await page.reload();
  await expect(page.getByTestId('phone-hod-hod_momo')).toBeVisible();

  await page.getByTestId('phone-scan-more').click();
  await page.getByRole('menuitemradio', { name: 'Running Up' }).click();
  await expect(page.getByTestId('phone-hod-running_up')).toContainText('2 stocks today');
  await expect(page.getByTestId('phone-hod-row-ZEBR')).toContainText('Running up');
  expect(await phoneOverflow(page)).toEqual([]);

  // The chip opens the Trader; the line over the list opens Notifications.
  await page.getByTestId('phone-hod-notify').click();
  await expect(page.getByTestId('phone-screen-notify')).toBeVisible();
  await page.goBack();
  await page.getByTestId('phone-chip-ZEBR').click();
  await expect(page).toHaveURL(/#\/trade\/ZEBR$/);

  expect(api.writes).toEqual([]);
  expect(api.unanswered.filter((p) => !p.startsWith('/api/luld/'))).toEqual([]);
  expect(errors).toEqual([]);
});

test('notifications: everything starts off; the PIN, the phone and the PC each have their part', async ({ page }, info) => {
  const { errors } = attachErrorCollector(page);
  await fakePush(page, 'granted');
  const api = await mockPhoneApi(page);
  await open(page, 'settings');
  const door = page.getByTestId('phone-settings-notify');
  await expect(door).toContainText('Off');
  expect(await phoneOverflow(page)).toEqual([]);
  await shot(page, info, '6-settings-row');
  await door.click();

  await expect(page.getByTestId('phone-screen-notify')).toBeVisible();
  const phone = page.getByRole('switch', { name: /^Notify this phone/ });
  await expect(phone).toHaveAttribute('aria-checked', 'false');
  for (const name of ['Setups on your stars', 'New leader', 'Fills', 'Loss limit']) {
    await expect(page.getByRole('switch', { name: new RegExp(`^${name}`) })).toHaveAttribute('aria-checked', 'false');
  }
  await expect(page.getByTestId('phone-notify-hod').getByRole('button', { name: 'Off' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('phone-notify-leader')).toContainText('A stock joins the top 3 Gainers');
  await expect(page.getByTestId('phone-notify-last')).toHaveText('Nothing sent yet');
  await expect(page.getByRole('button', { name: 'Send a test' })).toBeDisabled();
  expect(await phoneOverflow(page)).toEqual([]);
  expect(api.writes).toEqual([]);

  // Locked: the first tap asks for the PIN and subscribes nothing (Android asks only inside a tap).
  await phone.click();
  await typePin(page);
  await expect(page.getByTestId('phone-banner')).toContainText('tap the switch again');
  expect(await page.evaluate(() => (window as unknown as { __push: { asked: number } }).__push.asked)).toBe(0);

  await phone.click();
  await expect(page.getByTestId('phone-banner')).toContainText('This phone gets notifications');
  await expect(phone).toHaveAttribute('aria-checked', 'true');
  expect(api.writes.filter((w) => w.includes('/notify/'))).toEqual(['POST /api/phone/notify/key', 'POST /api/phone/notify/subscribe']);
  const push = await page.evaluate(() => (window as unknown as { __push: { asked: number; registered: string[]; subscribed: number } }).__push);
  expect(push).toMatchObject({ asked: 1, registered: ['/phone/sw.js'], subscribed: 1 });
  expect(api.notify.deviceIds).toHaveLength(1);

  // Each change sends the whole settings and shows what the PC kept.
  await page.getByTestId('phone-banner').click();
  await page.getByTestId('phone-notify-hod').getByRole('button', { name: 'Stars' }).click();
  await expect(page.getByTestId('phone-notify-hod').getByRole('button', { name: 'Stars' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('switch', { name: /^Fills/ }).click();
  await expect(page.getByRole('switch', { name: /^Fills/ })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'To: half an hour earlier' }).click();
  await expect(page.getByTestId('phone-notify-end')).toHaveText('15:30');
  const friday = page.getByTestId('phone-notify-days').getByRole('button', { name: 'Friday' });
  await friday.click();
  await expect(friday).toHaveAttribute('aria-pressed', 'false');
  expect(api.notify.saved.at(-1)).toEqual({ ...NOTIFY_DEFAULTS, hod_momo: 'stars', fills: true, end: '15:30', days: [0, 1, 2, 3] });

  await page.getByRole('button', { name: 'Send a test' }).click();
  await expect(page.getByTestId('phone-banner')).toContainText('Sent to 1 phone');
  await expect(page.getByTestId('phone-notify-last')).toContainText('Nova can reach this phone');
  await page.getByTestId('phone-banner').click();
  expect(await phoneOverflow(page)).toEqual([]);
  await shot(page, info, '5-notification-settings');

  // The row in Settings and the line over the HOD Momo list say the same.
  await page.getByRole('button', { name: 'Back to Settings' }).click();
  await expect(page.getByTestId('phone-settings-notify')).toContainText('On · Mon to Thu · 07:00 to 15:30');
  expect(await phoneOverflow(page)).toEqual([]);

  // Off again: the phone drops its address and the PC forgets it.
  await page.getByTestId('phone-settings-notify').click();
  await page.getByRole('switch', { name: /^Notify this phone/ }).click();
  await expect(page.getByTestId('phone-banner')).toContainText('This phone gets no notifications now');
  await expect(page.getByRole('switch', { name: /^Notify this phone/ })).toHaveAttribute('aria-checked', 'false');
  expect(api.notify.deviceIds).toEqual([]);
  expect(await page.evaluate(() => (window as unknown as { __push: { unsubscribed: number } }).__push.unsubscribed)).toBe(1);
  expect(SAMPLE_ENDPOINT).toContain('fcm.googleapis.com');
  expect(errors).toEqual([]);
});

test('a phone that blocked Nova, and a PC from before notifications, each say so', async ({ page }) => {
  await fakePush(page, 'denied', 'denied');
  await mockPhoneApi(page);
  await open(page, 'notify');
  const phone = page.getByRole('switch', { name: /^Notify this phone/ });
  await expect(phone).toBeDisabled();
  await expect(phone).toHaveAttribute('data-why', /blocked for Nova on this phone/);
  await expect(page.getByTestId('phone-notify-phone')).toContainText('Blocked for Nova');
  // The settings are still the PC's and still shown.
  await expect(page.getByTestId('phone-notify-hod')).toBeVisible();
  expect(await phoneOverflow(page)).toEqual([]);

  // An older backend has no such route: the screen says to update it, and draws no switches it cannot keep.
  await page.route('http://127.0.0.1:8000/api/phone/notify', (route) => route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not Found"}' }));
  await page.reload();
  await expect(page.getByTestId('phone-notify-absent')).toContainText('older than this page');
  await expect(page.getByTestId('phone-notify-hod')).toHaveCount(0);
  expect(await phoneOverflow(page)).toEqual([]);
});
