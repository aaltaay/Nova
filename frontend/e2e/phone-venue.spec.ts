import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { PHONE_PIN, mockPhoneApi, phoneOverflow } from './helpers/phoneApi';

// The phone's venue menu, the Sim strip and the Level 2 read (ADR 070 amendment 2026-11-13) against a stand-in API.
// Nothing here reaches a real backend: every switch below is one the stand-in records.
test.use({ viewport: { width: 360, height: 720 }, hasTouch: true });

async function typePin(page: Page) {
  const sheet = page.getByTestId('phone-pin-sheet');
  for (const digit of PHONE_PIN) await sheet.getByRole('button', { name: digit, exact: true }).click();
  await expect(sheet).toBeHidden();
}

test('the venue pill opens the menu, says what a switch would change, and a tap switches the desk', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  const api = await mockPhoneApi(page, { armed: true, effects: ['The desk is armed on Paper: switching disarms it'] });
  await page.goto('/phone.html#/trade/ABCD');
  await expect(page.getByTestId('phone-buy-market')).toBeVisible();

  await page.getByTestId('phone-venue').click();
  const menu = page.getByTestId('phone-venue-menu');
  await expect(menu).toBeVisible();
  await expect(menu.getByRole('menuitemradio')).toHaveCount(3);
  await expect(page.getByTestId('phone-venue-paper')).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('phone-venue-live')).toContainText('look only from the phone');
  await expect(page.getByTestId('phone-venue-stake')).toContainText('The desk is armed on Paper: switching disarms it');
  await expect(page.getByTestId('phone-venue-stake')).toContainText('Your own orders and shares stay on Paper.');
  expect(await phoneOverflow(page)).toEqual([]);
  // Opening the menu reads; it writes nothing.
  expect(api.writes).toEqual([]);

  // A tap outside closes it.
  await page.mouse.click(180, 600);
  await expect(menu).toBeHidden();

  // The switch is a write: a locked phone asks for the PIN, then the desk switches and the banner says so.
  await page.getByTestId('phone-venue').click();
  await page.getByTestId('phone-venue-sim').click();
  await typePin(page);
  await expect(page.getByTestId('phone-banner')).toContainText('Switched to Sim. The desk switched too.');
  await expect(page.getByTestId('phone-venue')).toHaveText('SIM');
  expect(api.writes).toEqual(['POST /api/phone/unlock', 'POST /api/phone/venue']);

  // On Sim at the live edge the screen stays live, the strip moves the desk's playhead, and the ticket trades.
  const strip = page.getByTestId('phone-sim-strip');
  await expect(strip).toContainText('live edge');
  await expect(page.getByTestId('phone-buy-market')).not.toHaveAttribute('data-why', /look only|Sim ·/);
  await page.getByTestId('phone-sim-play').click();
  await expect.poll(() => api.simMoves.length).toBe(1);
  expect(api.simMoves[0]).toEqual({ paused: true, symbol: 'ABCD' });
  await expect(strip).toContainText('paused');
  expect(await phoneOverflow(page)).toEqual([]);
  expect(errors).toEqual([]);
});

test("on Sim with another stock replaying, the desk's words take the book's place and the ticket sends nothing", async ({ page }) => {
  const api = await mockPhoneApi(page, {
    venue: 'sim', armed: true,
    simClock: { live_edge: false, replay_source: 'capture', replay_symbol: 'KLMN', replay_ok: true, session_date: '2026-11-12' },
  });
  await page.goto('/phone.html#/trade/ABCD');
  const note = page.getByTestId('phone-sim-note');
  await expect(note).toContainText('KLMN');
  await expect(page.getByTestId('phone-book')).toHaveCount(0);
  const buy = page.getByTestId('phone-buy-market');
  await expect(buy).toBeDisabled();
  await expect(buy).toContainText('Sim · nothing here');
  await expect(page.getByTestId('phone-sim-strip')).toContainText('Nov 12');
  expect(await phoneOverflow(page)).toEqual([]);
  expect(api.writes).toEqual([]);
});

test('the Level 2 read page fits the phone, and Back returns to Trade', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  const api = await mockPhoneApi(page);
  await page.goto('/phone.html#/book/ABCD');
  const read = page.getByTestId('phone-book-read');
  await expect(read).toBeVisible();
  await expect(read.locator('.ph-read__spread')).toContainText('4.81');
  await expect(read.locator('.ph-read__spread')).toContainText('4.82');
  expect(await phoneOverflow(page)).toEqual([]);
  await page.getByRole('button', { name: 'Back to Trade' }).click();
  await expect(page.getByTestId('phone-buy-market')).toBeVisible();
  expect(api.writes).toEqual([]);
  expect(errors).toEqual([]);
});

test('the marks switch in Settings turns the depth chart and the marks off on the book', async ({ page }) => {
  await mockPhoneApi(page);
  await page.goto('/phone.html#/settings');
  const marks = page.getByTestId('phone-settings-marks').getByRole('switch');
  await expect(marks).toHaveAttribute('aria-checked', 'true');
  expect(await phoneOverflow(page)).toEqual([]);
  await marks.click();
  await expect(marks).toHaveAttribute('aria-checked', 'false');
  await page.goto('/phone.html#/trade/ABCD');
  await expect(page.getByTestId('phone-book').locator('.ph-book__row')).not.toHaveCount(0);
  await expect(page.getByTestId('phone-depth-open')).toHaveCount(0);
});
