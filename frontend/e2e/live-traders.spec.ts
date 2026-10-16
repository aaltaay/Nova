import { expect, test, type Route } from '@playwright/test';
import { NOW_S } from '../src/demo/data/market';
import { botSession } from '../src/demo/data/pages';
import { capture, day, trade } from '../src/followed_traders/followedTestData';

/**
 * Bots > LiveTrader Bots (ADR 055; the followed traders' page since 2026-10-15, approved from a render) in a browser,
 * every API reply mocked: the LiveTrader Bots key in the head, each host's bot in the middle of their card, a copy as
 * a chip on the open row it copies, a host's key turned off in one press (off sells nothing, so nothing asks), an ask
 * answered from its toast, and the family's key turned off. Nothing reaches a backend or a broker: every write is
 * recorded and answered here. Made-up hosts and tickers.
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

/** The hosts' day: ALPHA holds XYZ (the bot's copy) and ABCD (none); BRAVO is on the bar with no trade yet. */
function followedDay() {
  const d = day({
    capture: capture({ traders: ['ALPHA', 'BRAVO'], bar: [
      { trader: 'ALPHA', image: null, positions: [{ side: 'long', symbol: 'XYZ', price: 100 }, { side: 'long', symbol: 'ABCD', price: 161.1 }] },
      { trader: 'BRAVO', image: null, positions: [] },
    ] }),
  });
  d.traders = [{
    ...d.traders[0],
    open: [
      trade({ id: 'r1', symbol: 'XYZ', entry: { first_price: 100, avg_price: 100, ts: NOW - 320, since_ts: null, known: true },
        now: { state: 'live', price: 100.44, trade_ts: NOW - 2, why: null }, pl: { per_share: 0.44, pct: 0.44 } }),
      trade({ id: 'r2', symbol: 'ABCD', entry: { first_price: 161.1, avg_price: 161.1, ts: NOW - 900, since_ts: null, known: true },
        now: { state: 'live', price: 161.95, trade_ts: NOW - 2, why: null }, pl: { per_share: 0.85, pct: 0.53 } }),
    ],
  }];
  return d;
}

test('LiveTrader Bots: the key in the head, each host\'s bot in its card, a key off in one press, an ask answered', async ({ page }) => {
  const errors: string[] = [];
  const writes: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  let alpha = hostCard();
  const bravo = hostCard({ name: 'BRAVO', positions: [], asks: [ASK], today: { pl_usd: -2.1, realized_usd: -2.1,
    unrealized_usd: 0, trades: 1, skipped: 1, series: [[NOW - 600, -2.1]] }, allowance: { used_usd: 0, of_usd: 2500 },
    settings: { ...hostCard().settings, entry: 'you', mode: 'approve' } });
  let asks = [ASK];
  let familyOn = true;
  const session = () => ({ ...botSession(NOW_S, 'paper'), keys: { venue: 'paper', error: null,
    strategy: { on: true, why_off: null }, live_trader: { on: familyOn, why_off: familyOn ? null : 'off' } } });
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });
  await page.route('http://127.0.0.1:8999/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() !== 'GET') {
      // The workspace's own focus sync (App.tsx's provider) is not the page's write.
      if (path !== '/api/bot/focus/sync') writes.push(`${req.method()} ${path} ${req.postData() ?? ''}`);
      if (path === '/api/bot/session/keys') {
        familyOn = JSON.parse(req.postData() ?? '{}').on === true;
        return json(route, session());
      }
      if (path.endsWith('/live-traders/ALPHA')) alpha = hostCard({ settings: { ...alpha.settings, key: false } });
      if (path.includes('/asks/')) asks = [];
      return json(route, cards([alpha, { ...bravo, asks }]));
    }
    if (path.endsWith('.jpg')) return route.fulfill({ status: 404, body: '' });
    if (path === '/api/followed-traders/config') return json(route, { schema_version: 1, enabled: true });
    if (path === '/api/followed-traders/day') return json(route, followedDay());
    if (path === '/api/bot/live-traders/asks') return json(route, { schema_version: 1, generated_at: NOW, asks, held: [] });
    if (path === '/api/bot/live-traders') return json(route, cards([alpha, { ...bravo, asks }]));
    if (path === '/api/bot/session') return json(route, session());
    // The bot's session is read only once the desk's venue is confirmed (its key reads that venue).
    if (path === '/api/ibkr/status') return json(route, { enabled: true, connected: true, mode: 'paper', venue: 'paper' });
    if (path === '/api/bot/proposals') return json(route, { proposals: [] });
    if (path === '/api/bot/audit') return json(route, { entries: [] });
    return json(route, {});
  });

  await page.goto('/e2e/fixtures/live-traders.html');
  await expect(page.getByTestId('ft-trader-ALPHA'), `browser errors: ${errors.join('; ')}`).toBeVisible();
  await expect(page.locator('.ft-head__title')).toHaveText('LiveTrader Bots');
  // The desk's Positions / Orders · today dock under the hosts (operator ask 2026-10-16).
  await expect(page.locator('[data-testid="stock-view-open-orders-dock"][data-dock-host="bots"]')).toBeVisible();
  // The family's key sits in the head, its words on hover.
  const key = page.getByTestId('bot-key-live_trader');
  await expect(page.getByTestId('bot-key-live_trader-line')).toHaveText('ON');
  await expect(page.getByTestId('bot-key-live_trader-line')).toHaveAttribute('data-tip', 'On: LiveTrader Bots may place orders on Paper.');
  await expect(key.locator('xpath=..')).toHaveAttribute('data-testid', 'lt-head');
  // Each host's bot in the middle of their card, on its own sheet: the chosen Entry is styled by it.
  const strip = page.getByTestId('lt-strip-ALPHA');
  await expect(strip.locator('xpath=..')).toHaveClass(/ft-trader__card--slot/);
  await expect(page.getByTestId('lt-entry-ALPHA-nova')).toHaveCSS('color', 'rgb(255, 255, 255)');
  await expect(page.getByTestId('lt-entry-BRAVO-you')).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('lt-allowance-ALPHA')).toHaveText('$954 of $2,500');
  await expect(page.getByTestId('lt-skips-ALPHA')).toHaveAttribute('data-tip', /large caps only/);
  // The copy is a chip on the open row it copies, and only there.
  await expect(page.getByTestId('ft-row-r1').getByTestId('lt-badge-r1')).toHaveText('BOT 4 sh');
  await expect(page.getByTestId('ft-row-r2').locator('.lt-badge')).toHaveCount(0);
  // BRAVO's ask takes its bot's second line.
  await expect(page.getByTestId('lt-ask-bravo-3')).toContainText('BRAVO shorted FADE at 40.00');

  // A host's key turns off in one press while its bot holds a copy: off sells nothing, so nothing asks.
  await page.getByTestId('lt-key-ALPHA').click();
  await expect(page.getByTestId('lt-key-ALPHA')).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByTestId('app-dialog')).toHaveCount(0);
  expect(writes).toEqual(['PATCH /api/bot/live-traders/ALPHA {"key":false}']);

  // The ask is a toast in the window too; Approve answers it.
  const toast = page.getByTestId('lt-ask-toast-bravo-3');
  await expect(toast).toContainText('Live Trader · BRAVO');
  await toast.getByTestId('lt-ask-toast-approve-bravo-3').click();
  await expect(toast).toHaveCount(0);
  expect(writes[1]).toBe('POST /api/bot/live-traders/BRAVO/asks/bravo-3 {"approve":true}');

  // The family key turns every host's bot off: off, they cannot place orders or sell.
  await page.getByTestId('bot-key-live_trader-switch').click();
  await expect(page.getByTestId('bot-key-live_trader-line')).toHaveText('OFF');
  await expect(page.getByTestId('bot-key-live_trader-line')).toHaveAttribute('data-tip', "Off: bots can't place orders or sell.");
  expect(writes[2]).toBe('POST /api/bot/session/keys {"family":"live_trader","on":false}');
  expect(errors).toEqual([]);
});
