import { expect, test, type Route } from '@playwright/test';
import { NOW_S } from '../src/demo/data/market';
import { botSession } from '../src/demo/data/pages';

/**
 * The Live Trader cards (ADR 055) in a browser, every API reply mocked: a host's card as the approved mockup draws
 * it, the key's question before it sells, and an ask answered from its toast. Nothing reaches a backend or a
 * broker: every write is recorded and answered here. Made-up hosts and tickers.
 */
const NOW = Date.now() / 1000;

function hostCard(over: Record<string, unknown> = {}) {
  return {
    name: 'ALPHA', face: null, on_air: true, left_ts: null,
    settings: { key: true, entry: 'nova', exit: 'nova', step_usd: 500, adds: 2, allowance_usd: 2500, sides: 'both',
      short_stop_pct: 5, take_open: true, mode: 'bot' },
    state: { tone: 'ok', text: 'On air · read 2 s ago' },
    allowance: { used_usd: 954, of_usd: 2500 },
    today: { pl_usd: 6.85, realized_usd: 3.52, unrealized_usd: 3.33, trades: 3, skipped: 2,
      series: [[NOW - 900, 1.2], [NOW - 400, 3.52], [NOW, 6.85]] },
    positions: [
      { id: 'ALPHA|long|XYZ', row_id: 'r1', symbol: 'XYZ', side: 'long', qty: 4, avg_cost: 100.02, their_avg: 100.0,
        now: 100.44, pl_usd: 1.68, steps: 1, adds_followed: 0, opened_ts: NOW - 300, state: 'open', order_id: null, note: null },
      { id: 'ALPHA|long|ABCD', row_id: 'r2', symbol: 'ABCD', side: 'long', qty: 3, avg_cost: 161.4, their_avg: 161.1,
        now: 161.95, pl_usd: 1.65, steps: 2, adds_followed: 1, opened_ts: NOW - 900, state: 'open', order_id: null, note: null },
    ],
    asks: [],
    events: [
      { ts: NOW - 60, tone: 'ok', outcome: 'order', symbol: 'XYZ', code: null, late_sec: 4,
        text: 'buy 4 XYZ at 100.04 -- ALPHA bought it at 100.00' },
      { ts: NOW - 30, tone: 'warn', outcome: 'skipped', symbol: 'QQQQ', code: 'LT_SMALL_CAP', late_sec: 3,
        text: 'a small cap ($2.1B): this bot copies large caps only ($10.0B and up)' },
    ],
    ...over,
  };
}

const ASK = { id: 'bravo-3', host: 'BRAVO', row_id: 'r9', symbol: 'FADE', side: 'short', step: 'entry', their_price: 40,
  qty: 12, limit: 39.97, stop: 41.97, created_ts: NOW - 5, expires_ts: NOW + 55, approved: false, answered: null,
  seconds_left: 55, text: 'BRAVO shorted FADE at 40.00: short 12 at 39.97, buy stop 41.97?' };

function cards(hosts: unknown[]) {
  return {
    schema_version: 1, generated_at: NOW, enabled: true, venue: 'paper', desk_venue: 'paper',
    can_trade: { ok: true, code: null, why: null }, sell_all_at: '15:55', sell_all_ts: null,
    watcher: { running: true, pass_ts: NOW, idle: false, text: 'Watching the bar, read 2 s ago',
      feed: { state: 'ok', error: null, read_age_sec: 2, behind_sec: 3, bar_visible: true, live: true } },
    settings_error: null, book_error: null, hosts, defaults: {}, bounds: {},
  };
}

test('the Live Trader cards: a host as drawn, the key asks before it sells, an ask answered from its toast', async ({ page }) => {
  const errors: string[] = [];
  const writes: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  let alpha = hostCard();
  const bravo = hostCard({ name: 'BRAVO', positions: [], asks: [ASK], today: { pl_usd: -2.1, realized_usd: -2.1,
    unrealized_usd: 0, trades: 1, skipped: 1, series: [[NOW - 600, -2.1]] }, allowance: { used_usd: 0, of_usd: 2500 },
    settings: { ...hostCard().settings, entry: 'you', mode: 'approve' } });
  let asks = [ASK];
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });
  await page.route('http://127.0.0.1:8999/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() !== 'GET') {
      writes.push(`${req.method()} ${path} ${req.postData() ?? ''}`);
      if (path.endsWith('/live-traders/ALPHA')) alpha = hostCard({ settings: { ...alpha.settings, key: false }, positions: [] });
      if (path.includes('/asks/')) asks = [];
      return json(route, cards([alpha, { ...bravo, asks }]));
    }
    if (path === '/api/followed-traders/config') return json(route, { schema_version: 1, enabled: true });
    if (path === '/api/bot/live-traders/asks') return json(route, { schema_version: 1, generated_at: NOW, asks, held: [] });
    if (path === '/api/bot/live-traders') return json(route, cards([alpha, { ...bravo, asks }]));
    if (path === '/api/bot/session') return json(route, botSession(NOW_S, 'paper'));
    if (path === '/api/bot/proposals') return json(route, { proposals: [] });
    if (path === '/api/bot/audit') return json(route, { entries: [] });
    return json(route, {});
  });

  await page.goto('/e2e/fixtures/live-traders.html');
  const section = page.getByTestId('bots-live-traders');
  await expect(section, `browser errors: ${errors.join('; ')}`).toContainText('Live Traders · TraderTV');
  await expect(page.getByTestId('lt-state-ALPHA')).toHaveText('On air · read 2 s ago');
  await expect(page.getByTestId('lt-mode-ALPHA')).toHaveText('bot enters · bot exits');
  await expect(page.getByTestId('lt-mode-BRAVO')).toHaveText('you approve · bot exits');
  await expect(page.getByTestId('lt-positions-ALPHA')).toContainText('ABCD');
  await expect(page.getByTestId('lt-events-ALPHA')).toContainText('large caps only');
  await expect(page.getByTestId('lt-ask-bravo-3')).toContainText('BRAVO shorted FADE at 40.00');

  // The key asks first, names what it sells, and sends nothing until "Sell 2 and turn off".
  await page.getByTestId('lt-key-ALPHA').click();
  const dialog = page.getByTestId('app-dialog');
  await expect(dialog).toContainText('XYZ 4 shares, ABCD 3 shares');
  await expect(page.getByTestId('app-dialog-confirm')).toHaveText('Sell 2 and turn off');
  expect(writes).toEqual([]);
  await page.getByTestId('app-dialog-confirm').click();
  await expect(page.getByTestId('lt-key-ALPHA')).toHaveAttribute('aria-checked', 'false');
  expect(writes).toEqual(['PATCH /api/bot/live-traders/ALPHA {"key":false}']);

  // The ask is a toast in the window too; Approve answers it.
  const toast = page.getByTestId('lt-ask-toast-bravo-3');
  await expect(toast).toContainText('Live Trader · BRAVO');
  await toast.getByTestId('lt-ask-toast-approve-bravo-3').click();
  await expect(toast).toHaveCount(0);
  expect(writes[1]).toBe('POST /api/bot/live-traders/BRAVO/asks/bravo-3 {"approve":true}');
  expect(errors).toEqual([]);
});
