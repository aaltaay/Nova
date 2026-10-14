import { expect, test, type Page, type WebSocketRoute } from '@playwright/test';

const NOW = 1_792_000_000;
const SYMBOL = 'FIXTURE';
const FIXTURE_PATH = '/e2e/fixtures/desk-freezes.html';
const API_BASE = process.env.NOVA_E2E_API_BASE ?? 'http://127.0.0.1:8999';

function hotList() {
  return {
    schema_version: 1, date: '2026-10-14', cap: 20, auto_cap: 20,
    auto: { n: 0, start: '07:00', end: '16:00', rule: 'Fixture rule', error: null },
    entries: [{ symbol: SYMBOL, how: 'star', at: NOW, board: null, rank: null,
      change_pct: null, followed: true, why_not_followed: null }],
    yesterday: ['PRIOR'], error: null,
  };
}

function book(seq: number, bid = 10, size = 1000) {
  return {
    type: 'book', symbol: SYMBOL, seq, at: NOW + seq / 1000, sent: NOW,
    data: {
      bids: Array.from({ length: 10 }, (_, i) => ({ price: +(bid - i / 100).toFixed(2), size, mm: 'TEST' })),
      asks: Array.from({ length: 10 }, (_, i) => ({ price: +(bid + (i + 1) / 100).toFixed(2), size, mm: 'TEST' })),
      l1_fallback: false,
    },
  };
}

function watch(pulled = 5800) {
  return { type: 'book_watch', symbol: SYMBOL, data: {
    schema_version: 1, now: NOW, reset: true, seq: pulled, watching: true, reason: null, window_sec: 60,
    sides: { bid: { pulled_shares: pulled, filled_shares: 100, large_pulls: 1 },
      ask: { pulled_shares: 0, filled_shares: 400, large_pulls: 0 } },
    drops: [{ seq: pulled, ts: NOW, side: 'bid', price: 9.98, pulled, filled: 0,
      outcome: 'pulled', large_pull: true, on_approach: false }],
  } };
}

function luld(upper = 10.08) {
  return { type: 'luld', symbol: SYMBOL, data: {
    schema_version: 1, symbol: SYMBOL, source: 'live', state: 'bands', exact: true,
    lower: 9.92, upper, reference: 10, reference_since: NOW - 20,
    reference_source: 'open', reference_words: 'the opening print', percent: '10%',
    prev_close: 10, tier: 2, tier_text: 'fixture Tier 2', tier_sure: true, spread: null,
    limit: null, straddle: null, anchor: { kind: 'open', ts: NOW - 20, price: 10 },
    halted_since: null, watching_since: NOW - 3600, warm_until: null, gap: null,
    last: 10, distance: { down_pct: -0.008, up_pct: 0.008 }, near: null, reason: null,
    history: [], note: "Nova's calculation", rules: 'Fixture published-rule input', track: null,
    as_of: NOW, text: 'Fixture bands', watching: true,
  } };
}

async function isolate(page: Page) {
  const errors: string[] = [];
  const unexpected: string[] = [];
  const sockets: WebSocketRoute[] = [];
  let reads = 0;
  let current = hotList();
  page.on('pageerror', error => {
    errors.push(`pageerror: ${error.message}`);
    console.error(`Fixture pageerror: ${error.message}`);
  });
  page.on('console', message => {
    if (message.type() === 'error') {
      errors.push(`console.error: ${message.text()}`);
      console.error(`Fixture console.error: ${message.text()}`);
    }
  });
  await page.route(`${API_BASE}/api/**`, async route => {
    unexpected.push(route.request().url());
    await route.fulfill({ status: 503, json: { error: 'Unexpected fixture API' } });
  });
  await page.route(`${API_BASE}/api/hot-list`, async route => {
    reads += 1;
    await route.fulfill({ json: current });
  });
  await page.route('**/__nova/**', async route => {
    unexpected.push(route.request().url());
    await route.fulfill({ status: 503, json: { error: 'Runtime operations forbidden in fixture' } });
  });
  await page.routeWebSocket(/\/ws\/ibkr\/depth\/FIXTURE(\?.*)?$/, socket => {
    sockets.push(socket);
    socket.send(JSON.stringify({ type: 'subscribed', symbol: SYMBOL, instance: 'fixture-instance' }));
    socket.send(JSON.stringify(book(1)));
  });
  return {
    errors, unexpected, sockets, reads: () => reads,
    changeList: () => { current = { ...hotList(), auto_cap: 21,
      entries: [{ ...hotList().entries[0], followed: false, why_not_followed: 'Fixture line unavailable' }] }; },
    send: (frame: unknown) => sockets[0].send(JSON.stringify(frame)),
  };
}

test('equal hot-list polls preserve the visible data and skip React commits in Chromium', async ({ page }) => {
  const fixture = await isolate(page);
  await page.clock.install({ time: new Date(NOW * 1000) });
  await page.goto(FIXTURE_PATH);
  await expect(page.getByTestId('hot-list-view')).toContainText('FIXTURE');
  const original = await page.getByTestId('hot-list-view').textContent();
  const originalCommits = await page.evaluate(() => window.deskFreezeFixture.metrics.hotCommits);
  for (let i = 2; i <= 4; i += 1) {
    await page.clock.fastForward(10_000);
    await expect.poll(fixture.reads).toBe(i);
    await expect(page.getByTestId('hot-list-view')).toHaveText(original!);
  }
  expect(await page.evaluate(() => window.deskFreezeFixture.metrics.hotCommits)).toBe(originalCommits);
  fixture.changeList();
  await page.clock.fastForward(10_000);
  await expect(page.getByTestId('hot-list-view')).toContainText('Fixture line unavailable');
  await expect(page.getByTestId('hot-list-view')).toContainText('"auto_cap":21');
  expect(await page.evaluate(() => window.deskFreezeFixture.metrics.hotCommits)).toBe(originalCommits + 1);
  expect(fixture.unexpected).toEqual([]);
  expect(fixture.errors).toEqual([]);
});

test('changed depth, annotations and hidden resume display their latest values and stamps in Chromium', async ({ page }) => {
  const fixture = await isolate(page);
  await page.clock.setFixedTime(new Date(NOW * 1000));
  await page.goto(FIXTURE_PATH);
  await expect(page.locator('.das-l2-bbo')).toContainText('10.00 × 10.01');
  fixture.send(watch());
  fixture.send(luld());
  await expect(page.getByTestId('l2-marker-stop')).toHaveClass(/--working/);
  await expect(page.getByTestId('l2-marker-entry')).toBeVisible();
  await expect(page.getByTestId('l2-marker-target')).toBeVisible();
  await expect(page.getByTestId('l2-pullmark-pulled')).toContainText('5,800');
  await expect(page.getByTestId('l2-pulls-bid')).toContainText('5.8K');
  await expect(page.getByTestId('l2-luld-ask')).toContainText('10.08');

  for (let seq = 2; seq <= 10; seq += 1) {
    fixture.send(book(seq, 10 + seq / 100, 1000 + seq));
    await expect.poll(() => page.evaluate(() => window.deskFreezeFixture.stamp().book?.seq)).toBe(seq);
    await expect(page.locator('.das-l2-side--bid .das-l2-row:not(.das-l2-row--luld)').first())
      .toContainText(`1,0${String(seq).padStart(2, '0')}`);
  }
  await expect(page.locator('.das-l2-bbo')).toContainText('10.10 × 10.11');
  expect(await page.evaluate(() => window.deskFreezeFixture.lock())).toBeNull();
  await page.getByRole('button', { name: 'Hide depth' }).click();
  const hiddenCommits = await page.evaluate(() => window.deskFreezeFixture.metrics.depthCommits);
  fixture.send(book(11, 10.25, 1200));
  fixture.send(book(12, 10.26, 1300));
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  expect(await page.evaluate(() => window.deskFreezeFixture.metrics.depthCommits)).toBe(hiddenCommits);
  expect(await page.evaluate(() => window.deskFreezeFixture.stamp().book?.seq)).toBe(10);
  await page.getByRole('button', { name: 'Show depth' }).click();
  await expect(page.locator('.das-l2-bbo')).toContainText('10.26 × 10.27');
  await expect.poll(() => page.evaluate(() => window.deskFreezeFixture.stamp().book?.seq)).toBe(12);
  fixture.send(watch(7200));
  fixture.send(luld(10.09));
  await expect(page.getByTestId('l2-pullmark-pulled')).toContainText('7,200');
  await expect(page.getByTestId('l2-luld-ask')).toContainText('10.09');
  expect(fixture.sockets).toHaveLength(1);
  expect(fixture.unexpected).toEqual([]);
  expect(fixture.errors).toEqual([]);
});
