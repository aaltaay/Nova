import fs from 'node:fs';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { e2eTickerDetail, mockLiveTraderApi } from './helpers/liveTraderApi';
import { APUS_NOW, apusAt, apusHistoryWire, apusReadWire } from '../src/stock_read/stockReadFixtures';

/**
 * Who trades the stock (ADR 037) on the live Trader route with a mocked API: APUS on 2026-09-24 at
 * 15:03 ET. The Buy / Sell row sits right above Level 2 and Level 2 keeps its room at 1080; the chart
 * carries the chip, the trade's track and the call (ENTER NOW at the trigger); an approved bracket
 * held draws its stop and target solid and puts ENTRY / STOP / TARGET in the Level 2 book.
 * `NOVA_E2E_SHOTS=<dir>` saves screenshots for a visual check. Nothing reaches a broker.
 */

const SHOTS = process.env.NOVA_E2E_SHOTS ?? '';
const SETUP_ID = 'APUS-2026-09-24-1790276460@bull_flag';

interface Bar { t: string; o: number; h: number; l: number; c: number; v: number }

function et(h: number, m: number, s = 0): string {
  return new Date(Date.UTC(2026, 8, 24, h + 4, m, s)).toISOString();
}

/** 13:00-15:03 one-minute candles: a fade to 5.15, a three-candle pole to 5.45, a flag and the break. */
function minuteBars(): Bar[] {
  const out: Bar[] = [];
  let px = 5.95;
  for (let i = 0; i < 119; i += 1) {
    const drift = -0.0065 + Math.sin(i / 5) * 0.012;
    const o = px;
    const c = Math.max(5.12, px + drift);
    out.push({ t: et(13 + Math.floor(i / 60), i % 60), o: +o.toFixed(2), h: +(Math.max(o, c) + 0.02).toFixed(2),
      l: +(Math.min(o, c) - 0.02).toFixed(2), c: +c.toFixed(2), v: 40_000 + (i % 7) * 9_000 });
    px = c;
  }
  out.push({ t: et(14, 59), o: 5.12, h: 5.23, l: 5.09, c: 5.22, v: 310_000 });
  out.push({ t: et(15, 0), o: 5.22, h: 5.36, l: 5.2, c: 5.34, v: 420_000 });
  out.push({ t: et(15, 1), o: 5.34, h: 5.45, l: 5.32, c: 5.43, v: 380_000 });
  out.push({ t: et(15, 2), o: 5.43, h: 5.43, l: 5.33, c: 5.36, v: 150_000 });
  out.push({ t: et(15, 3), o: 5.36, h: 5.47, l: 5.36, c: 5.45, v: 260_000 });
  return out;
}

function aggregate(bars: Bar[], minutes: number): Bar[] {
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i += minutes) {
    const chunk = bars.slice(i, i + minutes);
    out.push({ t: chunk[0].t, o: chunk[0].o, h: Math.max(...chunk.map(b => b.h)), l: Math.min(...chunk.map(b => b.l)),
      c: chunk[chunk.length - 1].c, v: chunk.reduce((n, b) => n + b.v, 0) });
  }
  return out;
}

function tenSecondBars(): Bar[] {
  const out: Bar[] = [];
  let px = 5.4;
  for (let i = 0; i < 24; i += 1) {
    const o = px;
    const c = +(px + Math.sin(i / 2) * 0.02 + 0.002).toFixed(2);
    out.push({ t: et(15, 0, i * 10), o, h: +(Math.max(o, c) + 0.01).toFixed(2), l: +(Math.min(o, c) - 0.01).toFixed(2), c,
      v: 8_000 });
    px = c;
  }
  return out;
}

const bid = (price: number, size: number) => ({ price, size, side: 'bid', mm: 'NSDQ' });
const ask = (price: number, size: number) => ({ price, size, side: 'ask', mm: 'ARCA' });
const BOOK = {
  bids: [bid(5.43, 800), bid(5.42, 1200), bid(5.40, 300), bid(5.38, 2500), bid(5.36, 900), bid(5.35, 400),
    bid(5.33, 1800), bid(5.30, 700), bid(5.28, 500), bid(5.25, 3000)],
  asks: [ask(5.44, 600), ask(5.45, 900), ask(5.46, 1500), ask(5.48, 400), ask(5.50, 5200), ask(5.52, 700),
    ask(5.55, 1100), ask(5.58, 300), ask(5.60, 2000), ask(5.62, 800)],
  l1_fallback: false,
};

/** The bull flag armed at 5.43 and triggered two seconds before the page's clock. */
function triggeredRead() {
  return {
    ...apusReadWire,
    price: 5.45,
    setups: apusReadWire.setups.map(lane => (lane.setup_type !== 'bull_flag' ? lane : {
      ...lane, state: 'triggered', reason: 'triggered at 5.43 with the tape at go', forming: null,
      setup: { trigger: 5.43, entry: 5.44, stop: 5.33, risk: 0.11, target1: 5.66, pullback_bars: 1,
        armed_bar_t: apusAt(15, 2), triggered_at: APUS_NOW - 2, trigger_price: 5.43 },
    })),
    plan: { ...apusReadWire.plan, setup_id: SETUP_ID, state: 'triggered', provisional: false, grade: 'B',
      tape: { verdict: 'go', reasons: ['buyers lifting the ask'] } },
  };
}

function modeView(mode: string, over: Record<string, unknown> = {}) {
  const sides: Record<string, [string, string]> = {
    signal: ['you', 'you'], approve: ['you', 'nova'], auto_entry: ['nova', 'you'], bot: ['nova', 'nova'],
  };
  const [buy, sell] = sides[mode];
  return {
    schema_version: 1, symbol: 'APUS', generated_at: Date.now() / 1000, venue: 'paper', mode, buy, sell,
    risk_usd: mode === 'auto_entry' ? 20 : null, set_at: null, locks: { buy: null, sell: null }, notes: [],
    approval: null, trade: null, nova_entries_today: 0, last_event: null, bot: null, ...over,
  };
}

interface Opts {
  read?: () => unknown;
  price?: number;
  positions?: unknown[];
  view?: () => Record<string, unknown>;
}

async function openApus(page: Page, opts: Opts = {}): Promise<{ puts: unknown[] }> {
  const puts: unknown[] = [];
  let current = opts.view?.() ?? modeView('signal');
  await page.clock.setFixedTime(new Date(APUS_NOW * 1000));
  await mockLiveTraderApi(page, { bars: false, positions: opts.positions ?? [] });
  const one = minuteBars();
  const byTf: Record<string, Bar[]> = {
    '1Min': one,
    '5Min': aggregate(one, 5),
    '10Sec': tenSecondBars(),
    '1Day': apusHistoryWire.daily.map(b => ({ t: `${b.d}T04:00:00.000Z`, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v })),
  };
  await page.route('**/api/ticker/APUS/bars*', async route => {
    const tf = new URL(route.request().url()).searchParams.get('timeframe') ?? '1Min';
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ bars: byTf[tf] ?? one, coverage: null }) });
  });
  await page.route('**/api/ticker/APUS', route => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify(e2eTickerDetail('APUS', opts.price ?? 5.37, 2.29)) }));
  await page.route('**/api/stock-read/APUS/decisions*', route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify({ ...apusReadWire, events: [], summary: null }) }));
  await page.route('**/api/stock-read/APUS/history*', route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify(apusHistoryWire) }));
  await page.route(/\/api\/stock-read\/APUS(\?.*)?$/, route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify(opts.read?.() ?? apusReadWire) }));
  await page.route('**/api/stock-mode/APUS', async route => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON() as { buy: string; sell: string };
      puts.push(body);
      const mode = body.buy === 'nova' ? (body.sell === 'nova' ? 'bot' : 'auto_entry')
        : (body.sell === 'nova' ? 'approve' : 'signal');
      current = modeView(mode);
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(current) });
  });
  await page.routeWebSocket('**/ws/ibkr/depth/APUS', socket => {
    socket.send(JSON.stringify({ type: 'subscribed', symbol: 'APUS' }));
    socket.send(JSON.stringify({ type: 'book', symbol: 'APUS', data: BOOK }));
  });
  await page.goto('/?view=stock&symbol=APUS');
  await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible({ timeout: 20_000 });
  return { puts };
}

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

test.describe('Who trades the stock', () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test('sits right above Level 2, keeps Level 2 its room, and hands the buy to Nova', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { puts } = await openApus(page);
    const row = page.getByTestId('who-trades');
    await expect(row).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('who-trades-mode')).toHaveText('Signal only');
    const rowBox = await row.boundingBox();
    const l2Box = await page.getByTestId('stock-view-depth-side-by-side').boundingBox();
    expect(rowBox && l2Box && rowBox.y + rowBox.height <= l2Box.y + 1).toBe(true);
    expect(l2Box && l2Box.height).toBeGreaterThan(250);
    // The plan in the book, dashed while it is only a plan: the entry with the asks it would take,
    // the stop among the bids, the target past the rows shown.
    await expect(page.getByTestId('l2-marker-entry')).toHaveClass(/das-l2-marker--plan/);
    await expect(page.getByTestId('l2-marker-stop')).toBeVisible();
    await expect(page.getByTestId('l2-marker-target')).toContainText('TARGET 5.66 ↓');
    await expect(page.getByTestId('who-trades-chip')).toContainText('Signal only');
    await shot(page, 'who-signal');

    await page.getByTestId('who-trades-buy-nova').click();
    await expect(page.getByTestId('who-trades-mode')).toHaveText('Auto-entry');
    expect(puts).toEqual([{ buy: 'nova', sell: 'you', risk_usd: 20 }]);
    await expect(page.getByTestId('who-trades-chip')).toContainText('Nova buys · you sell');
    await shot(page, 'who-auto-entry');

    await page.getByTestId('who-trades-chip').click();
    await expect(page.getByTestId('who-trades-menu')).toBeVisible();
    await shot(page, 'who-chip-menu');
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('says ENTER NOW at the trigger, on the chart and in words', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openApus(page, { read: triggeredRead, price: 5.45 });
    const call = page.getByTestId('moment-call');
    await expect(call).toContainText('ENTER NOW · 5.44', { timeout: 20_000 });
    await expect(call).toContainText('181 shares risk $20. Your click.');
    await expect(page.getByTestId('stock-read-badge')).toHaveText('BULL FLAG · TRIGGERED');
    await expect(page.getByTestId('moment-track').getByText('Trigger')).toHaveAttribute('data-state', 'now');
    await expect(page.getByTestId('who-trades')).toBeVisible();
    await shot(page, 'who-enter-now');
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('an approved bracket held: its orders solid, the exit Nova holds, and the way to take it over', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const trade = {
      kind: 'approve', state: 'holding', venue: 'paper', venue_day: '2026-09-24', setup_id: SETUP_ID,
      setup_type: 'bull_flag', qty: 181, entry: 5.44, stop: 5.33, target: 5.66, entry_order_id: 101,
      target_order_id: 102, stop_order_id: 103, fill_price: 5.44, filled_at: APUS_NOW - 5, exit_price: null,
      exit_reason: null, exits: 'nova', sent_at: APUS_NOW - 6, closed_at: null, note: null, exiting: false,
    };
    await openApus(page, {
      read: triggeredRead,
      price: 5.50,
      positions: [{ symbol: 'APUS', qty: 181, market_price: 5.5, market_value: 995.5, avg_cost: 5.44,
        unrealized_pnl: 10.86, realized_pnl: 0 }],
      view: () => modeView('approve', { trade, approval: { setup_id: SETUP_ID, setup_type: 'bull_flag', entry: 5.44,
        stop: 5.33, target: 5.66, qty: 181, approved_at: APUS_NOW - 90, state: 'sent', reason: null } }),
    });
    await expect(page.getByTestId('stock-read-badge')).toHaveText('IN THE TRADE · +$10.86', { timeout: 20_000 });
    await expect(page.getByTestId('moment-track').getByText('Target / stop')).toHaveAttribute('data-state', 'next');
    await expect(page.getByTestId('moment-call')).toContainText('BOUGHT 181 @ 5.44');
    await expect(page.getByTestId('l2-marker-stop')).toHaveClass(/das-l2-marker--working/);
    await expect(page.getByTestId('l2-marker-target')).toHaveClass(/das-l2-marker--working/);
    await expect(page.getByTestId('stock-read-action-take-over-line')).toHaveText('Take over');
    // Past the rows shown, the target still shows: a level takes no row of the ladder's fixed height.
    await expect(page.getByTestId('l2-marker-target')).toBeInViewport();
    if (SHOTS) await page.waitForTimeout(700); // the position tag follows its line on its next measure
    await shot(page, 'who-approve-held');
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
