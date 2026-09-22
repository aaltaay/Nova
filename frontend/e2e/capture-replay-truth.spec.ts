import { expect, test } from '@playwright/test';

test('failed capture selection is visible and empty sessions cannot navigate the desk', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  let rejected = false;
  let loaded = false;
  const clock = () => ({
    sim: true, paused: true, minute_from_open: 120, minute_max: 960,
    replay_source: loaded ? 'capture' : 'synthetic',
    replay_date: loaded ? '2026-09-19' : null,
    replay_symbol: loaded ? 'GOOD' : null,
    replay_ok: !rejected,
    replay_error: rejected ? 'Capture contains no usable data' : null,
  });
  await page.route('http://127.0.0.1:8999/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === '/api/sim/replay') {
      const symbol = route.request().postDataJSON().symbol;
      loaded = symbol === 'GOOD';
      rejected = symbol === 'GONE';
      body = clock();
    } else if (path === '/api/sim/clock') body = clock();
    else if (path === '/api/sim/history') body = { jobs: [], default_date: '2026-09-18' };
    else if (path === '/api/capture/sessions') body = {
      days: [{ date: '2026-09-19', ticker_count: 3 }],
      tickers_by_day: { '2026-09-19': [
        { symbol: 'EMPTY', prints: 0, l2: 0, empty: true, usable: false, unavailable_reason: 'No recorded prints or quotes' },
        { symbol: 'GONE', prints: 10, l2: 0, empty: false, usable: true },
        { symbol: 'GOOD', prints: 10, l2: 0, empty: false, usable: true },
      ] },
    };
    await route.fulfill({ json: body });
  });
  await page.goto('/e2e/fixtures/sim-session.html');
  await page.getByRole('button', { name: 'Open IMCC', exact: true }).click();
  // On the Trader view the Day / Ticker pickers live in the strip's ⋯ menu;
  // the failed-selection alert is a chip on the strip itself, outside the menu.
  await page.getByTestId('sim-strip-menu').click();
  await page.getByTestId('sim-replay-day').selectOption('2026-09-19');
  await expect(page.getByTestId('sim-replay-ticker').locator('option[value="EMPTY"]')).toHaveJSProperty('disabled', true);
  await page.getByTestId('sim-replay-ticker').selectOption('GONE');
  await expect(page.getByRole('alert')).toContainText('Capture contains no usable data');
  await expect(page.getByTestId('sim-replay-source')).not.toHaveText('CAPTURE');
  await expect(page.getByTestId('desk-active')).toHaveText('IMCC');
  await expect(page.getByTestId('desk-tabs')).toHaveText('IMCC');
  await page.getByTestId('sim-replay-day').selectOption('2026-09-19');
  await page.getByTestId('sim-replay-ticker').selectOption('GOOD');
  await expect(page.getByTestId('desk-active')).toHaveText('GOOD');
  await expect(page.getByTestId('sim-replay-source')).toHaveText('CAPTURE');
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(errors).toEqual([]);
});
