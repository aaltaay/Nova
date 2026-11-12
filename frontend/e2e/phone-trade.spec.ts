import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { PHONE_PIN, mockPhoneApi, phoneOverflow } from './helpers/phoneApi';

// The phone's Trade screen (ADR 070, amendment 2026-11-12) against a stand-in API. Nothing here reaches a real
// backend: every order below is one the stand-in records.
test.use({ viewport: { width: 360, height: 720 }, hasTouch: true });

async function openTrade(page: Page) {
  await page.goto('/phone.html#/trade/ABCD');
  await expect(page.getByTestId('phone-buy-market')).toBeVisible();
  // The book has been drawn, so an order has a view to say it was priced from.
  await expect(page.getByTestId('phone-book').locator('.ph-book__row')).not.toHaveCount(0);
}

async function typePin(page: Page) {
  const sheet = page.getByTestId('phone-pin-sheet');
  for (const digit of PHONE_PIN) await sheet.getByRole('button', { name: digit, exact: true }).click();
  await expect(sheet).toBeHidden();
}

test('Trade shows the book and the tape the desk sends, and fits the phone in every ticket', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  const api = await mockPhoneApi(page, { armed: true });
  await openTrade(page);
  const book = page.getByTestId('phone-book');
  // The top of book, and as many rows as the box holds: no more.
  await expect(book.locator('.ph-book__top')).toContainText('4.81');
  await expect(book.locator('.ph-book__top')).toContainText('spread 0.01');
  const rows = await book.locator('.ph-book__row').count();
  expect(rows).toBeGreaterThanOrEqual(10);
  expect(rows).toBeLessThan(15);
  await expect(book.locator('.ph-book__row').first()).toContainText('NSDQ');
  await expect(book.locator('.ph-book__row').first()).toContainText('1.2K');
  await expect(page.getByTestId('phone-tape').locator('.ph-tape__row').first()).toHaveAttribute('data-side', /ask|bid/);
  await expect(page.getByTestId('phone-fresh')).toHaveAttribute('data-tone', 'good');
  expect(await phoneOverflow(page)).toEqual([]);

  // What a button sends is written on it, read from the same book.
  await expect(page.getByTestId('phone-buy-limit')).toContainText('limit 4.87 · +0.05');
  await expect(page.getByTestId('phone-sell-50-ask')).toContainText('SELL ½ 250');
  await expect(page.getByTestId('phone-sell-100-bid')).toContainText('hit Bid 4.81');

  await page.getByRole('button', { name: 'Custom', exact: true }).first().click();
  await expect(page.getByTestId('phone-send')).toContainText('Buy 100 · Limit 4.87');
  expect(await phoneOverflow(page)).toEqual([]);

  // The grab handle trades chart height for book rows.
  const chart = page.locator('.ph-trade__chart');
  const small = (await chart.boundingBox())?.height ?? 0;
  await page.getByTestId('phone-chart-handle').click();
  await expect.poll(async () => (await chart.boundingBox())?.height ?? 0).toBeGreaterThan(small + 60);
  expect(await book.locator('.ph-book__row').count()).toBeLessThan(rows);
  expect(await phoneOverflow(page)).toEqual([]);

  // Looking sends nothing.
  expect(api.writes).toEqual([]);
  expect(errors).toEqual([]);
});

test('a tap is the order: the desk gets its own order body, priced from the book on the screen', async ({ page }) => {
  const api = await mockPhoneApi(page, { armed: true });
  await openTrade(page);

  await page.getByRole('button', { name: '500', exact: true }).click();
  await page.getByTestId('phone-buy-market').click();
  // A locked phone asks for its PIN first; the order goes once, after it.
  await typePin(page);
  const banner = page.getByTestId('phone-banner');
  // Sent, then Filled as soon as the position moves: on Paper a market order fills at once.
  await expect(banner).toContainText(/Sent · Buy 500 market|Filled · Bought 500 ABCD/);
  await expect.poll(() => api.orders.length).toBe(1);
  const buy = api.orders[0];
  expect(buy).toMatchObject({ symbol: 'ABCD', side: 'BUY', qty: 500, order_type: 'MKT' });
  // ADR 045: the order says which book it was priced from, on the PC's clock.
  expect(buy.view).toMatchObject({ instance: 'stand-in-backend', book: { seq: 4, bid: 4.81, ask: 4.82 } });
  expect(Math.abs((buy.view?.action_wall_ms ?? 0) - Date.now())).toBeLessThan(5_000);
  expect(buy.client_timing?.action_wall_ms).toBeGreaterThan(0);
  // The position changed: the banner says the fill.
  await expect(banner).toContainText('Filled · Bought 500 ABCD', { timeout: 10_000 });
  await expect(banner).toContainText('Now long 1,000');

  // A limit over the Ask, with the Ask it was read from.
  await page.getByTestId('phone-buy-limit').click();
  await expect.poll(() => api.orders.length).toBe(2);
  expect(api.orders[1]).toMatchObject({ side: 'BUY', qty: 500, order_type: 'LMT', limit_price: 4.87, reference_price: 4.82 });

  // Sell all at the Ask rests: it becomes a working order, and the orders dot counts it.
  await expect(page.getByTestId('phone-sell-100-ask')).toContainText('SELL ALL 1,500', { timeout: 10_000 });
  await page.getByTestId('phone-sell-100-ask').click();
  await expect.poll(() => api.orders.length).toBe(3);
  expect(api.orders[2]).toMatchObject({ side: 'SELL', qty: 1500, order_type: 'LMT', limit_price: 4.82 });
  await expect(page.getByTestId('phone-dot-ord')).toContainText('2', { timeout: 10_000 });

  // Every write went through the phone's own door.
  expect(api.writes.every((w) => w.startsWith('POST /api/phone/'))).toBe(true);
});

test('a locked padlock sends nothing, says so, and the banner opens it', async ({ page }) => {
  const api = await mockPhoneApi(page);
  await openTrade(page);
  await expect(page.getByTestId('phone-trade-locked')).toBeVisible();
  await page.getByTestId('phone-buy-market').click({ force: true });
  const banner = page.getByTestId('phone-banner');
  await expect(banner).toContainText('NOT SENT · Padlock is locked');
  expect(api.orders).toEqual([]);
  expect(api.writes).toEqual([]);
  await banner.click();
  await typePin(page);
  await expect(page.getByTestId('phone-trade-locked')).toBeHidden();
  expect(api.state.armed).toBe(true);
});

test('Custom sends a stop under the bid, and a refusal is the desk\'s words and stays', async ({ page }) => {
  const api = await mockPhoneApi(page, { armed: true });
  await openTrade(page);
  await page.getByRole('button', { name: 'Set a stop…' }).click();
  const send = page.getByTestId('phone-send');
  // The desk's default stop: 1% under the bid, for every share held.
  await expect(send).toContainText('Sell 500 · Stop 4.76');
  await page.getByRole('button', { name: 'Price down' }).click();
  await expect(send).toContainText('Stop 4.75');
  await send.click();
  await typePin(page);
  await expect.poll(() => api.orders.length).toBe(1);
  expect(api.orders[0]).toMatchObject({ side: 'SELL', qty: 500, order_type: 'STP', stop_price: 4.75 });
  await expect(page.getByTestId('phone-banner')).toContainText('Sent · Sell 500 stop 4.75');

  // The padlock closes on the desk: the next order is refused there, in its words, and the banner stays.
  api.state.armed = false;
  await page.getByRole('button', { name: 'Buy', exact: true }).click();
  await page.getByRole('button', { name: 'Market', exact: true }).click();
  await page.getByTestId('phone-send').click({ force: true });
  const banner = page.getByTestId('phone-banner');
  await expect(banner).toContainText('NOT SENT');
  await page.waitForTimeout(5_000);
  await expect(banner).toBeVisible();
});

test('hold the position dot to flatten, behind a warning; cancel all reaches every stock', async ({ page }) => {
  const api = await mockPhoneApi(page, { armed: true });
  await openTrade(page);
  const dot = page.getByTestId('phone-dot-pos');
  await expect(dot).toBeVisible();
  // A tap shows what it holds.
  await dot.click();
  await expect(page.getByTestId('phone-dot-pop')).toContainText('Long 500 at 4.71');
  await dot.click();
  await expect(page.getByTestId('phone-dot-pop')).toBeHidden();
  // Press and hold: the warning, and nothing sent until it is answered.
  const box = await dot.boundingBox();
  if (!box) throw new Error('no dot');
  await page.mouse.move(box.x + box.width / 2 - 3, box.y + box.height / 2 + 3);
  await page.mouse.down();
  const ask = page.getByTestId('phone-ask');
  await expect(ask).toBeVisible();
  await page.mouse.up();
  await expect(ask).toContainText('Flatten ABCD?');
  await expect(ask).toContainText('Sells all 500 shares at the Bid, 4.81');
  expect(api.writes).toEqual([]);
  await ask.getByRole('button', { name: 'Keep position' }).click();
  await expect(ask).toBeHidden();
  expect(api.writes).toEqual([]);

  await dot.click();
  await page.getByTestId('phone-dot-pop').getByRole('button', { name: /^Flatten 500/ }).click();
  await page.getByTestId('phone-ask-yes').click();
  await typePin(page);
  // The desk's own Cancel + Flatten: the stock's orders, then the whole position as a protective flatten.
  await expect.poll(() => api.orders.length).toBe(1);
  expect(api.cancels[0]).toContain('symbol=ABCD');
  expect(api.orders[0]).toMatchObject({ side: 'SELL', qty: 500, intent: 'flatten' });
  await expect(dot).toBeHidden({ timeout: 10_000 });

  // Cancel all: every stock, after the same warning.
  api.state.working = [11, 12];
  await expect(page.getByTestId('phone-dot-ord')).toContainText('2', { timeout: 10_000 });
  await page.getByTestId('phone-cancel-all').click();
  await expect(ask).toContainText('2 working orders will be cancelled');
  await page.getByTestId('phone-ask-yes').click();
  await expect.poll(() => api.cancels.length).toBe(2);
  expect(api.cancels[1]).toContain('all_symbols=true');
  await expect(page.getByTestId('phone-banner')).toContainText('Cancelled 2 order(s)');
});

test('a book that arrives late holds the buys and says why; a sell still goes', async ({ page }) => {
  const api = await mockPhoneApi(page, { armed: true, book: 'behind' });
  await openTrade(page);
  const lag = page.getByTestId('phone-lag');
  await expect(lag).toBeVisible({ timeout: 10_000 });
  await expect(lag).toContainText('Level 2 is behind the market');
  await expect(page.getByTestId('phone-fresh')).toHaveAttribute('data-tone', 'down');
  await expect(page.getByTestId('phone-fresh')).toContainText('1.4 s');
  const buy = page.getByTestId('phone-buy-market');
  await expect(buy).toBeDisabled();
  await expect(buy).toContainText('held · feed behind');
  await expect(buy).toHaveAttribute('data-why', /behind the market/);
  expect(await phoneOverflow(page)).toEqual([]);
  // Getting out is never held for lag.
  await page.getByTestId('phone-sell-100-bid').click();
  await typePin(page);
  await expect.poll(() => api.orders.length).toBe(1);
  expect(api.orders[0]).toMatchObject({ side: 'SELL', qty: 500, order_type: 'LMT' });
});

test('off Paper the ticket is drawn and locked, and says the phone trades Paper only', async ({ page }) => {
  const api = await mockPhoneApi(page, { venue: 'sim', armed: true });
  await openTrade(page);
  const buy = page.getByTestId('phone-buy-market');
  await expect(buy).toBeDisabled();
  await expect(buy).toHaveAttribute('data-why', /the phone trades Paper only/);
  await expect(page.getByTestId('phone-sell-100-bid')).toBeDisabled();
  await expect(page.getByTestId('phone-cancel-all')).toBeDisabled();
  expect(api.writes).toEqual([]);
});

test('the Trade tab with no stock chosen says how to choose one, and remembers the last one traded', async ({ page }) => {
  await mockPhoneApi(page, { armed: true });
  await page.goto('/phone.html#/trade');
  await expect(page.getByTestId('phone-trade-pick')).toBeVisible();
  await page.goto('/phone.html#/trade/ABCD');
  await expect(page.getByTestId('phone-buy-market')).toBeVisible();
  await page.getByTestId('phone-tabs').getByRole('button', { name: 'Home' }).click();
  await page.getByTestId('phone-tabs').getByRole('button', { name: 'Trade' }).click();
  await expect(page.getByTestId('phone-buy-market')).toBeVisible();
  await expect(page.locator('.ph-trade__head')).toContainText('ABCD');
});
