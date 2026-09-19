import { expect, test } from '@playwright/test';

test('actual candle series follows replay time, clears on rewind and ignores a future quote', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => { errors.push(error.message); console.error(error.message); });
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  let minute = 2;
  let calls = 0;
  let paused = false;
  const rows = Array.from({ length: 4 }, (_, i) => ({
    t: `2026-09-18T10:0${i}:00Z`, o: 10 + i, h: 12 + i, l: 9 + i, c: 11 + i, v: 100,
  }));
  await page.route('http://127.0.0.1:8999/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === '/api/ibkr/status') body = { mode: 'sim', enabled: true, connected: true };
    if (path === '/api/sim/clock') {
      if (route.request().method() === 'POST') {
        const action = route.request().postDataJSON();
        if ('minute_from_open' in action) minute = action.minute_from_open;
        if ('paused' in action) paused = action.paused;
      }
      body = { sim: true, paused, minute_from_open: minute, minute_max: 720,
        sim_time_et: `2026-09-18T06:${String(minute).padStart(2, '0')}:00-04:00`, replay_source: 'synthetic' };
    }
    if (path === '/api/capture/sessions') body = { days: [], tickers_by_day: {} };
    if (path.endsWith('/bars')) {
      calls++;
      body = { bars: rows.slice(0, minute), coverage: { replay: true, replay_mode: 'completed_bars', filling: false } };
    }
    await route.fulfill({ json: body });
  });
  await page.goto('/e2e/fixtures/replay-chart.html?external-api=1');
  const painted = page.getByTestId('painted');
  // Cold Vite compilation is separate from the chart's one-second replay poll.
  await expect(painted).toBeVisible({ timeout: 15_000 });
  await expect.poll(async () => JSON.parse(await painted.innerText()).length).toBe(2);
  await expect(painted).not.toContainText('999');
  const before = calls;
  minute = 3;
  await expect.poll(async () => JSON.parse(await painted.innerText()).length).toBe(3);
  expect(calls).toBeGreaterThan(before);
  await page.getByRole('button', { name: 'Pause Sim time' }).click();
  const slider = page.getByTestId('sim-session-scrubber');
  await slider.focus();
  await page.keyboard.press('Home');
  await expect(painted).toHaveText('[]');
  await expect(page.getByTestId('indicators')).toHaveText('[]');
  await expect(page.getByTestId('vwap')).toHaveText('[]');
  await expect(page.getByTestId('error')).toHaveText('No bars available at this replay time');
  await page.keyboard.press('ArrowRight');
  await expect.poll(async () => JSON.parse(await painted.innerText()).length).toBe(1);
  await expect(painted).not.toContainText('999');
  expect(errors).toEqual([]);
});

test('the fixture opens with sample data without Playwright API interception', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/e2e/fixtures/replay-chart.html');
  const painted = page.getByTestId('painted');
  await expect(painted).toBeVisible({ timeout: 15_000 });
  await expect.poll(async () => JSON.parse(await painted.innerText()).length).toBe(2);
  await page.getByRole('button', { name: 'Advance sample minute' }).click();
  await expect.poll(async () => JSON.parse(await painted.innerText()).length).toBe(3);
  await page.getByTestId('sim-session-scrubber').focus();
  await page.keyboard.press('Home');
  await expect(painted).toHaveText('[]');
  expect(errors).toEqual([]);
});

test('opening HTML directly explains how to run the fixture', async ({ page }) => {
  await page.goto(`file://${process.cwd().replaceAll('\\', '/')}/e2e/fixtures/replay-chart.html`);
  await expect(page.getByText('This test fixture needs the Vite dev server')).toBeVisible();
  await expect(page.getByRole('link', { name: 'the replay chart fixture' })).toHaveAttribute(
    'href', 'http://127.0.0.1:5173/e2e/fixtures/replay-chart.html',
  );
});
