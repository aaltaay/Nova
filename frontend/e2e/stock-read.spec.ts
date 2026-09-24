import fs from 'node:fs';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { e2eTickerDetail, mockLiveTraderApi } from './helpers/liveTraderApi';
import {
  apusDecisionsWire,
  apusHistoryWire,
  apusReadWire,
} from '../src/stock_read/stockReadFixtures';

/**
 * The bot's read on one stock (ADR 036) on the live Trader route with a mocked API: APUS at 15:03
 * ET on 2026-09-24, the bull flag's pole up and one flag candle closed. The rail carries the plan
 * and the tiles; the 1-minute chart the flag, the plan's zones and the legend; the sheet every
 * signal, the day and the history. `NOVA_E2E_SHOTS=<dir>` saves screenshots for a visual check.
 */

const SHOTS = process.env.NOVA_E2E_SHOTS ?? '';

/** ET wall clock that day -> ISO (EDT, UTC-4). */
function et(h: number, m: number, s = 0): string {
  return new Date(Date.UTC(2026, 8, 24, h + 4, m, s)).toISOString();
}

interface Bar { t: string; o: number; h: number; l: number; c: number; v: number }

/** 13:00-15:02 one-minute candles: a slow fade to 5.15, a three-candle pole to 5.45, one flag candle. */
function minuteBars(): Bar[] {
  const out: Bar[] = [];
  let px = 5.95;
  for (let i = 0; i < 119; i += 1) {
    const h = 13 + Math.floor(i / 60);
    const m = i % 60;
    const drift = -0.0065 + Math.sin(i / 5) * 0.012;
    const o = px;
    const c = Math.max(5.12, px + drift);
    out.push({ t: et(h, m), o: +o.toFixed(2), h: +(Math.max(o, c) + 0.02).toFixed(2),
      l: +(Math.min(o, c) - 0.02).toFixed(2), c: +c.toFixed(2), v: 40_000 + (i % 7) * 9_000 });
    px = c;
  }
  out.push({ t: et(14, 59), o: 5.12, h: 5.23, l: 5.09, c: 5.22, v: 310_000 });
  out.push({ t: et(15, 0), o: 5.22, h: 5.36, l: 5.2, c: 5.34, v: 420_000 });
  out.push({ t: et(15, 1), o: 5.34, h: 5.45, l: 5.32, c: 5.43, v: 380_000 });
  out.push({ t: et(15, 2), o: 5.43, h: 5.43, l: 5.33, c: 5.36, v: 150_000 });
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
    const c = +(px + Math.sin(i / 2) * 0.02 - 0.002).toFixed(2);
    out.push({ t: et(14, 59, 0 + i * 10), o, h: +(Math.max(o, c) + 0.01).toFixed(2), l: +(Math.min(o, c) - 0.01).toFixed(2), c,
      v: 8_000 });
    px = c;
  }
  return out;
}

/** `readFor(url)` answers each read (the forming flag by default). */
async function openApus(page: Page, readFor: (url: string) => unknown = () => apusReadWire) {
  await mockLiveTraderApi(page, { bars: false, positions: [] });
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
    body: JSON.stringify(e2eTickerDetail('APUS', 5.37, 2.29)) }));
  await page.route('**/api/stock-read/APUS/decisions*', route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify(apusDecisionsWire) }));
  await page.route('**/api/stock-read/APUS/history*', route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify(apusHistoryWire) }));
  await page.route(/\/api\/stock-read\/APUS(\?.*)?$/, route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify(readFor(route.request().url())) }));
  await page.goto('/?view=stock&symbol=APUS');
  await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible({ timeout: 20_000 });
}

/** A hand plan at `entry` with the backend's 3-candle stop, or the stop the query names. */
function manualRead(url: string) {
  const q = new URL(url).searchParams;
  const entry = Number(q.get('entry'));
  const stop = q.get('stop') ? Number(q.get('stop')) : 5.31;
  const risk = +(entry - stop).toFixed(4);
  return {
    ...apusReadWire,
    plan: {
      ...apusReadWire.plan, source: 'manual', setup_type: null, kind: null, state: 'manual', trigger: null,
      provisional: true, entry, stop, target: +(entry + 2 * risk).toFixed(4), risk, reward: 2 * risk, rr: 2,
      entry_rule: 'your entry', target_rule: 'entry + 2 x risk',
      stop_rule: q.get('stop') ? 'your stop' : 'the lowest low of the last 3 closed 1-min candles',
      reason: 'no setup is forming: your entry, a 2:1 target', window: null, marks: [],
      checks: [{ id: 'risk', state: 'ok', text: `risk ${risk.toFixed(2)} within the 0.20 cap` }],
    },
  };
}

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

test.describe("The bot's read on one stock", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test('puts the plan and the tiles above Level 2 and the flag on the 1-minute chart', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openApus(page);

    const plan = page.getByTestId('stock-read-plan');
    await expect(plan).toBeVisible({ timeout: 20_000 });
    // At 1080 the quote card has no room for the whole plan and Level 2 both: one line first.
    await expect(plan).toContainText('FLAG 1/2');
    await expect(page.getByTestId('stock-read-plan-line')).toHaveText('5.44/5.33/5.66 · 181 sh');
    await expect(page.getByTestId('stock-read-stage-line')).toBeVisible();
    await expect(page.getByTestId('stock-read-tile-setups')).toContainText('Flag 1/2');
    const l2 = await page.getByTestId('stock-view-depth-side-by-side').boundingBox();
    expect(l2 && l2.height).toBeGreaterThan(250);
    await shot(page, 'desk-line');
    await page.getByTestId('stock-read-plan-fold').click();
    await expect(plan).toContainText('Bull flag');
    await expect(plan).toContainText('FORMING 1/2');
    await expect(page.getByTestId('stock-read-entry')).toHaveText('5.44');
    await expect(page.getByTestId('stock-read-stop')).toHaveText('5.33');
    await expect(page.getByTestId('stock-read-target')).toHaveText('5.66');
    await expect(page.getByTestId('stock-read-size')).toHaveText('181 sh');
    await expect(page.getByTestId('stock-read-strip').locator('.sr-tile')).toHaveCount(8);

    // The plan sits between the quote stats and Level 2, and every stat row stays on screen.
    const stats = await page.getByTestId('stock-view-quote-stats').boundingBox();
    const planBox = await plan.boundingBox();
    expect(stats && planBox && planBox.y >= stats.y + stats.height - 1).toBe(true);
    const clipped = await page.getByTestId('stock-view-quote-stats').evaluate(el => {
      const card = el.closest('.sv-module-card__body') as HTMLElement | null;
      const bottom = card ? card.getBoundingClientRect().bottom : Infinity;
      return Array.from(el.querySelectorAll('.cq-cell')).some(c => c.getBoundingClientRect().bottom > bottom + 0.5);
    });
    expect(clipped).toBe(false);

    const legend = page.getByTestId('stock-read-legend');
    await expect(legend).toBeVisible();
    await expect(page.getByTestId('stock-read-legend-bull_flag')).toContainText('Bull flag 1/2');
    await expect(page.getByTestId('stock-read-badge')).toHaveText('BULL FLAG · FORMING 1 OF 2');
    await expect(page.getByTestId('stock-read-legend-gap_and_go')).toHaveAttribute('data-why', /No scanner yet/);
    await shot(page, 'desk');

    await page.getByTestId('stock-read-tile-front').hover();
    await expect(page.getByTestId('stock-read-popover')).toContainText('MACD 1-minute');
    await shot(page, 'hover-front');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test("opens every signal, the bot's day and the history in the sheet", async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openApus(page);
    await page.getByTestId('stock-read-all').click();
    const sheet = page.getByTestId('stock-read-sheet');
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText('APUS at 15:03 ET');
    await shot(page, 'sheet-signals');

    await page.getByTestId('stock-read-tab-decisions').click();
    await expect(page.getByTestId('stock-read-event')).toHaveCount(4);
    await shot(page, 'sheet-decisions');

    await page.getByTestId('stock-read-tab-history').click();
    await expect(page.getByTestId('stock-read-runs')).toBeVisible();
    await shot(page, 'sheet-history');

    await page.getByTestId('stock-read-tab-decisions').click();
    await page.getByTestId('stock-read-event').nth(3).getByText('show on chart ›').click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByTestId('stock-read-focus')).toContainText('15:01');
    await shot(page, 'focus');
    await page.getByTestId('stock-read-focus-clear').click();
    await expect(page.getByTestId('stock-read-focus')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('plans a hand trade when nothing is forming, and its stop drags on the 1-minute chart', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const asked: string[] = [];
    // The operator opened the whole plan before (the switch is kept).
    await page.addInitScript(() => localStorage.setItem('nova.stockRead.layers',
      JSON.stringify({ schema_version: 1, value: { setups: true, levels: true, hidden: [], plan: 'open' } })));
    await openApus(page, url => {
      if (!url.includes('?entry=')) return { ...apusReadWire, plan: null };
      asked.push(url);
      return manualRead(url);
    });
    const typed = page.getByTestId('stock-read-entry-type');
    await expect(typed).toBeVisible({ timeout: 20_000 });
    // No depth line in this test: the ask is not known, so its button says why.
    await expect(page.getByTestId('stock-read-entry-ask')).toHaveAttribute('data-why', /No ask/);
    await typed.fill('5.39');
    await typed.press('Enter');
    await expect(page.getByTestId('stock-read-entry-input')).toHaveValue('5.39');
    await expect(page.getByTestId('stock-read-target')).toHaveText('5.55');
    await expect(page.getByTestId('stock-read-badge')).toHaveText('YOUR PLAN');

    // Find the stop line by the cursor it gives, then drag it down.
    const pane = page.getByTestId('ticker-chart-1Min').locator('.chart-body');
    const box = await pane.boundingBox();
    if (!box) throw new Error('the 1-minute pane has no box');
    const x = box.x + box.width * 0.5;
    let stopY = -1;
    for (let y = Math.round(box.y + box.height * 0.2); y < box.y + box.height * 0.95; y += 1) {
      await page.mouse.move(x, y);
      const cursor = await pane.evaluate(el => (el as HTMLElement).style.cursor);
      if (cursor === 'ns-resize') stopY = y; // the last grab-able line from the top is the stop
    }
    expect(stopY).toBeGreaterThan(0);
    await page.mouse.move(x, stopY);
    await page.mouse.down();
    await page.mouse.move(x, stopY + 12, { steps: 4 });
    await page.mouse.up();
    await expect.poll(() => asked.some(u => /stop=/.test(u))).toBe(true);
    const last = new URL(asked.filter(u => /stop=/.test(u)).pop() as string).searchParams;
    expect(Number(last.get('entry'))).toBe(5.39);
    expect(Number(last.get('stop'))).toBeLessThan(5.31);
    await expect(page.getByTestId('stock-read-plan-note')).toContainText('drag the entry or stop');
    await shot(page, 'manual');

    await page.getByTestId('stock-read-clear-manual').click();
    await expect(page.getByTestId('stock-read-entry-type')).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
