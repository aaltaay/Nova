import { expect, test } from '@playwright/test';

test('scrubbing preserves IMCC with AAPL closed; explicit replay picks still navigate', async ({ page }) => {
  let minute = 120;
  let replaySymbol = 'AAPL';
  let scrubPosts = 0;
  let paused = false;
  const clock = () => ({
    sim: true, paused, replay_source: 'capture', replay_date: '2026-09-19',
    replay_symbol: replaySymbol, minute_from_open: minute, minute_max: 960,
  });
  await page.route('http://127.0.0.1:8999/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === '/api/sim/clock') {
      if (route.request().method() === 'POST') {
        const action = route.request().postDataJSON();
        if ('paused' in action) paused = action.paused;
        else {
          minute = action.minute_from_open;
          scrubPosts++;
        }
      }
      body = clock();
    } else if (path === '/api/sim/replay') {
      replaySymbol = route.request().postDataJSON().symbol;
      body = clock();
    } else if (path === '/api/sim/history') {
      body = { jobs: [], default_date: '2026-09-18' };
    } else if (path.startsWith('/api/sim/history/snapshot/')) {
      body = { active: false };
    } else if (path === '/api/capture/sessions') {
      body = {
        days: [{ date: '2026-09-19', ticker_count: 2 }],
        tickers_by_day: { '2026-09-19': [
          { symbol: 'AAPL', prints: 100, l2: 10 },
          { symbol: 'IMCC', prints: 100, l2: 10 },
        ] },
      };
    }
    await route.fulfill({ json: body });
  });
  await page.goto('/e2e/fixtures/sim-session.html');
  await page.getByRole('button', { name: 'Open AAPL', exact: true }).click();
  await page.getByRole('button', { name: 'Open IMCC', exact: true }).click();
  await page.getByRole('button', { name: 'Close AAPL', exact: true }).click();
  await expect(page.getByTestId('desk-tabs')).toHaveText('IMCC');
  // The Ticker picker sits in the Trader strip's ⋯ menu; the transport and the
  // band are on the strip itself, so the menu is closed before touching them.
  const menu = page.getByTestId('sim-strip-menu');
  await menu.click();
  await expect(page.getByTestId('sim-replay-ticker')).toHaveValue('AAPL');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('sim-replay-ticker')).toHaveCount(0);
  await page.getByRole('button', { name: 'Pause Sim time' }).click();
  await expect(page.getByRole('button', { name: 'Play Sim time' })).toBeVisible();
  const slider = page.getByTestId('sim-session-scrubber');
  const box = (await slider.boundingBox())!;
  await page.mouse.move(box.x + box.width / 6, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => scrubPosts).toBeGreaterThan(0);
  await expect(page.getByTestId('desk-active')).toHaveText('IMCC');
  await expect(page.getByTestId('desk-tabs')).toHaveText('IMCC');
  await slider.focus();
  const beforeKeyboard = scrubPosts;
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => scrubPosts).toBeGreaterThan(beforeKeyboard);
  await expect(page.getByTestId('desk-tabs')).toHaveText('IMCC');
  await expect(page.getByTestId('desk-active')).toHaveText('IMCC');
  await menu.click();
  await page.getByTestId('sim-replay-ticker').selectOption('IMCC');
  await page.getByTestId('sim-replay-ticker').selectOption('AAPL');
  await expect(page.getByTestId('desk-active')).toHaveText('AAPL');
  // Preview tabs (ADR 011, stock_view/traderTabsState.ts): the pick opens AAPL in
  // the preview tab, replacing the unpinned IMCC instead of piling up a tab.
  await expect(page.getByTestId('desk-tabs')).toHaveText('AAPL');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Play Sim time' })).toBeVisible();
  await page.getByRole('button', { name: 'Play Sim time' }).click();
  await expect(page.getByRole('button', { name: 'Pause Sim time' })).toBeVisible();
});
