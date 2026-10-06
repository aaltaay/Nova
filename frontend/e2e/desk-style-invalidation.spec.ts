import { expect, test, type Locator } from '@playwright/test';

const FIXTURE = '/e2e/fixtures/desk-style-invalidation.html';

test.beforeEach(async ({ page }) => {
  await page.route('http://127.0.0.1:8999/**', route => route.fulfill({ json: {} }));
});

test('live tape updates do not restyle unrelated desk elements', async ({ page, browserName }, testInfo) => {
  test.skip(browserName !== 'chromium', 'Style element counts come from Chromium tracing.');
  await page.goto(FIXTURE);
  await expect(page.getByTestId('print-count')).toHaveText('0');
  await expect(page.locator('.ts-row').first()).toContainText('6.00');
  const canaries = await page.getByTestId('style-canary').count();
  const before = await page.getByTestId('style-canary').allTextContents();
  // Let the first layout/ResizeObserver settle before measuring only print updates.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Tracing.start', { categories: 'devtools.timeline', transferMode: 'ReturnAsStream' });
  for (let count = 1; count <= 8; count += 1) {
    await page.evaluate(() => window.dispatchEvent(new Event('desk-style-print')));
    await expect(page.getByTestId('print-count')).toHaveText(String(count));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  }
  const complete = new Promise<{ stream?: string }>(resolve => cdp.once('Tracing.tracingComplete', resolve));
  await cdp.send('Tracing.end');
  const { stream } = await complete;
  if (!stream) throw new Error('Chromium returned no trace stream.');
  let raw = '';
  for (;;) {
    const chunk = await cdp.send('IO.read', { handle: stream });
    raw += chunk.data;
    if (chunk.eof) break;
  }
  await cdp.send('IO.close', { handle: stream });
  await cdp.detach();
  const trace = JSON.parse(raw) as { traceEvents: Array<{ name: string; args?: { elementCount?: number } }> };
  const counts = trace.traceEvents.filter(e => e.name === 'UpdateLayoutTree')
    .map(e => e.args?.elementCount).filter((count): count is number => typeof count === 'number');
  await testInfo.attach('style-element-counts', {
    body: JSON.stringify({ canaries, counts }), contentType: 'application/json',
  });
  expect(counts.length, 'the trace must actually capture style recalculation').toBeGreaterThan(0);
  // A full-document restyle necessarily includes all 500 unrelated canaries.
  // Leave generous room for real tape/Desk styles without a CPU timing threshold.
  expect(Math.max(...counts), `affected element counts: ${counts.join(', ')}`).toBeLessThan(canaries / 2);
  await expect(page.locator('.ts-row').first()).toContainText('6.08');
  expect(await page.getByTestId('style-canary').allTextContents()).toEqual(before);
});

async function catalystVisibility(row: Locator, visible: boolean) {
  const values = await row.locator('.scanner-col--catalyst > *').evaluateAll(nodes => nodes.map(el => getComputedStyle(el).visibility));
  expect(values.length).toBeGreaterThan(0);
  expect(values).toEqual(values.map(() => visible ? 'visible' : 'hidden'));
}

test('Desk Catalyst text yields only to hover or visible keyboard focus', async ({ page }) => {
  await page.goto(FIXTURE);
  const row = page.getByTestId('desk-board-row-FIX');
  const absent = page.getByTestId('desk-board-row-VOID');
  const text = await row.locator('.scanner-col--catalyst').textContent();
  await page.mouse.move(0, 0);
  await catalystVisibility(row, true);
  await catalystVisibility(absent, true);
  await row.hover();
  await catalystVisibility(row, false);
  await absent.hover();
  await catalystVisibility(absent, false);
  await page.mouse.move(0, 0);
  await page.getByTestId('focus-start').focus();
  await page.keyboard.press('Tab');
  await expect(row).toBeFocused();
  await catalystVisibility(row, false);
  await page.keyboard.press('Tab');
  await expect(page.getByTestId('desk-board-watch-FIX')).toBeFocused();
  await catalystVisibility(row, false);
  // A mouse-focused action must release the Catalyst after the pointer leaves.
  await page.getByTestId('desk-board-watch-FIX').evaluate(el => (el as HTMLElement).blur());
  await row.hover();
  await page.getByTestId('desk-board-record-FIX').click();
  await page.mouse.move(0, 0);
  await catalystVisibility(row, true);
  expect(await row.locator('.scanner-col--catalyst').textContent()).toBe(text);
  await expect(page.getByTestId('opened-symbol')).toHaveText('');
  await page.getByTestId('focus-start').focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('opened-symbol')).toHaveText('FIX');
});

test('AlertDialog media keeps its responsive title column', async ({ page }) => {
  for (const width of [639, 640, 1000]) {
    await page.setViewportSize({ width, height: 800 });
    for (const size of ['default', 'sm']) for (const media of [false, true]) {
      await page.goto(`${FIXTURE}?size=${size}&media=${media ? '1' : '0'}`);
      await page.getByRole('button', { name: 'Open fixture dialog' }).click();
      const title = page.getByRole('heading', { name: 'Fixture confirmation' });
      await expect(title).toBeVisible();
      expect(await title.evaluate(el => getComputedStyle(el).gridColumnStart), `${width}/${size}/media=${media}`)
        .toBe(width >= 640 && size === 'default' && media ? '2' : 'auto');
      await page.getByRole('button', { name: 'Cancel fixture' }).click();
      await expect(title).toHaveCount(0);
    }
  }
});

test('the shared title change preserves practice order review and cancel/confirm', async ({ page }) => {
  await page.goto(FIXTURE);
  await page.getByRole('button', { name: 'Review practice order' }).click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('BUY 10 FIX on Paper (fixture)');
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId('order-confirmations')).toHaveText('0');
  await page.getByRole('button', { name: 'Review practice order' }).click();
  await dialog.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId('order-confirmations')).toHaveText('1');
});
