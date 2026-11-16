import fs from 'node:fs';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { e2eTickerDetail, mockLiveTraderApi } from './helpers/liveTraderApi';
import { APUS_NOW, apusAt, apusHistoryWire, apusReadWire } from '../src/stock_read/stockReadFixtures';

/**
 * The trade's moment (ADR 037) on the live Trader route with a mocked API: APUS on 2026-09-24 at 15:03 ET. Level 2
 * keeps its room at 1080 and carries the plan as ENTRY / STOP / TARGET / T2, dashed while it is only a plan; the chart
 * carries the trade's track and the call (ENTER NOW at the trigger); shares held turn the entry solid. The tab never
 * asks who trades the stock: the strategies only watch (ADR 072).
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

interface Opts {
  read?: () => unknown;
  price?: number;
  positions?: unknown[];
}

/** The Trader on APUS; `asked` lists every URL the page requests, to prove what it never asks for. */
async function openApus(page: Page, opts: Opts = {}): Promise<{ mutations: string[]; asked: string[] }> {
  const asked: string[] = [];
  page.on('request', request => { asked.push(request.url()); });
  await page.clock.setFixedTime(new Date(APUS_NOW * 1000));
  const { mutations } = await mockLiveTraderApi(page, { bars: false, positions: opts.positions ?? [] });
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
  // The depth socket carries ?tab=1&front=N (ADR 044 decision 6); a glob would not match the query.
  await page.routeWebSocket(/\/ws\/ibkr\/depth\/APUS(\?.*)?$/, socket => {
    socket.send(JSON.stringify({ type: 'subscribed', symbol: 'APUS' }));
    socket.send(JSON.stringify({ type: 'book', symbol: 'APUS', data: BOOK }));
  });
  await page.goto('/?view=stock&symbol=APUS');
  await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible({ timeout: 20_000 });
  return { mutations, asked };
}

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

test.describe("The trade's moment on the Trader", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test('puts the plan in Level 2, keeps Level 2 its room, and never asks who trades the stock', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { mutations, asked } = await openApus(page);
    const l2 = page.getByTestId('stock-view-depth-side-by-side');
    await expect(l2).toBeVisible({ timeout: 20_000 });
    const l2Box = await l2.boundingBox();
    expect(l2Box && l2Box.height).toBeGreaterThan(250);
    // The plan in the book, dashed while it is only a plan: the entry with the asks it would take,
    // the stop among the bids, target 1 at the plan's own 5.49 (#845: targets replace 2R).
    await expect(page.getByTestId('l2-marker-entry')).toHaveClass(/das-l2-marker--plan/);
    await expect(page.getByTestId('l2-marker-stop')).toBeVisible();
    await expect(page.getByTestId('l2-marker-target')).toContainText('TARGET 5.49');
    // Target 2 sits past the rows shown and still shows: a level takes no row of the ladder's fixed height.
    await expect(page.getByTestId('l2-marker-target2')).toContainText('T2 5.99');
    await expect(page.getByTestId('l2-marker-target2')).toBeInViewport();
    // No Who trades row or chip, and no stock-mode request: the strategies only watch (ADR 072).
    await expect(page.getByTestId('who-trades')).toHaveCount(0);
    await expect(page.getByTestId('who-trades-chip')).toHaveCount(0);
    expect(asked.filter(u => u.includes('/api/stock-mode'))).toEqual([]);
    await shot(page, 'trade-plan');
    expect(mutations).toEqual([]);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('says ENTER NOW at the trigger, on the chart and in words', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { mutations } = await openApus(page, { read: triggeredRead, price: 5.45 });
    const call = page.getByTestId('moment-call');
    await expect(call).toContainText('ENTER NOW · 5.44', { timeout: 20_000 });
    await expect(call).toContainText('181 shares risk $20. Your click.');
    await expect(page.getByTestId('stock-read-badge')).toHaveText('BULL FLAG · TRIGGERED');
    await expect(page.getByTestId('moment-track').getByText('Trigger')).toHaveAttribute('data-state', 'now');
    await shot(page, 'trade-enter-now');
    expect(mutations).toEqual([]);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('shares held: the entry turns solid, and the sell is yours alone', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { mutations } = await openApus(page, {
      read: triggeredRead,
      price: 5.50,
      positions: [{ symbol: 'APUS', qty: 181, market_price: 5.5, market_value: 995.5, avg_cost: 5.44,
        unrealized_pnl: 10.86, realized_pnl: 0 }],
    });
    await expect(page.getByTestId('stock-read-badge')).toContainText('IN THE TRADE', { timeout: 20_000 });
    await expect(page.getByTestId('moment-track').getByText('Holding')).toHaveAttribute('data-state', 'now');
    await expect(page.getByTestId('moment-track').getByText('Your exit')).toHaveAttribute('data-state', 'next');
    // The entry is in effect; the stop and target stay a plan: no order of Nova's stands behind them (ADR 072).
    await expect(page.getByTestId('l2-marker-entry')).toHaveClass(/das-l2-marker--working/);
    await expect(page.getByTestId('l2-marker-stop')).toHaveClass(/das-l2-marker--plan/);
    await expect(page.getByTestId('l2-marker-target')).toHaveClass(/das-l2-marker--plan/);
    // The plan card's one button while you hold is your own Stage sell: folded it says so, open it names the shares.
    await expect(page.getByTestId('stock-read-action-stage-sell-line')).toHaveText('Stage sell');
    await page.getByTestId('stock-read-plan-fold').click();
    await expect(page.getByTestId('stock-read-action-stage-sell')).toContainText('Stage sell 181');
    await expect(page.locator('[data-testid^="stock-read-action-"]')).toHaveCount(1);
    await expect(page.getByTestId('held-nova-exit')).toHaveCount(0);
    await expect(page.getByTestId('stock-read-action-take-over-line')).toHaveCount(0);
    if (SHOTS) await page.waitForTimeout(700); // the position tag follows its line on its next measure
    await shot(page, 'trade-held');
    expect(mutations).toEqual([]);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('a long plan scrolls, and Level 2 keeps its spread row and its room', async ({ page }) => {
    // Operator report, 2026-11-13: on a tall desk a long plan left Level 2 under the 260 px where it drops
    // the bid / spread / ask row and its rows sit at their floor.
    await page.setViewportSize({ width: 2560, height: 1440 });
    const longRead = () => ({
      ...apusReadWire,
      plan: { ...apusReadWire.plan, checks: [
        ...(apusReadWire.plan?.checks ?? []),
        ...Array.from({ length: 10 }, (_, i) => ({ id: `long-${i}`, state: 'warn',
          text: `one more line the plan carries on a busy stock, number ${i + 1}, long enough to fill the row` })),
      ] },
    });
    await openApus(page, { read: longRead });
    await expect(page.getByTestId('stock-read-entry')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('l2-spread')).toBeVisible();
    await expect(page.getByTestId('l2-spread-bid')).toHaveText('5.43');
    await expect(page.getByTestId('l2-spread-ask')).toHaveText('5.44');
    const pane = await page.locator('.sv-md-pane__live').first().boundingBox();
    expect(pane && pane.height).toBeGreaterThanOrEqual(260);
    const rail = await page.getByTestId('stock-read-rail')
      .evaluate(el => ({ scroll: el.scrollHeight, client: el.clientHeight }));
    expect(rail.scroll).toBeGreaterThan(rail.client);
    await shot(page, 'trade-long-plan');
  });
});
