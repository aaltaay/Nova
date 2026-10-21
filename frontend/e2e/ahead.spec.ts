import fs from 'node:fs';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { e2eTickerDetail, mockLiveTraderApi } from './helpers/liveTraderApi';
import readyWire from '../src/ahead/__fixtures__/answer_ready.json' with { type: 'json' };
import notSetUpWire from '../src/ahead/__fixtures__/answer_not_set_up.json' with { type: 'json' };
import statusWire from '../src/ahead/__fixtures__/status_ready.json' with { type: 'json' };
import noStatusWire from '../src/ahead/__fixtures__/status_not_configured.json' with { type: 'json' };
import { AHEAD_WORDS } from '../src/ahead/aheadConstants';
import { apusReadWire } from '../src/stock_read/stockReadFixtures';

/**
 * Ahead (ADR 061) on the live Trader route with a mocked API: APUS's 1-minute candles to 15:02 ET on 2026-09-24 and
 * made-up forecaster answers (Nova Marketing Sample Data; the numbers mean nothing). The switch is off by default; on,
 * the zone's words say why the AI view is hidden until "Show before it has earned it" is on, the panel's scopes
 * work, and a desk with no forecaster still carries Nova's own lines on to where they meet. `NOVA_E2E_SHOTS=<dir>` saves
 * screenshots for a visual check.
 */

const SHOTS = process.env.NOVA_E2E_SHOTS ?? '';

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

/** ET wall clock that day -> epoch seconds (EDT, UTC-4). */
function et(h: number, m: number): number {
  return Date.UTC(2026, 8, 24, h + 4, m) / 1000;
}

interface Bar { t: string; o: number; h: number; l: number; c: number; v: number }

/** 13:00-15:02 one-minute candles, every minute, closing at 5.36. */
function minuteBars(): Bar[] {
  const out: Bar[] = [];
  for (let i = 0; i <= 122; i += 1) {
    const c = +(5.36 + Math.sin(i / 6) * 0.04).toFixed(2);
    const last = i === 122;
    out.push({ t: new Date(et(13, i) * 1000).toISOString(), o: c, h: +(c + 0.02).toFixed(2), l: +(c - 0.02).toFixed(2),
      c: last ? 5.36 : c, v: 40_000 });
  }
  return out;
}

const BAR_T = et(15, 2);
const SHIFT = 5.36 - 4.62;

/** The ready fixture moved onto APUS's last candle and price (the forecaster has not passed its exam). */
function readyAnswer() {
  const a = structuredClone(readyWire);
  const move = (rows: number[][]) => rows.map(r => r.map(x => +(x + SHIFT).toFixed(4)));
  return {
    ...a, symbol: 'APUS', bar_t: BAR_T, as_of: BAR_T + 60, generated_at: BAR_T + 65, price: 5.36,
    ai: { ...a.ai, close: move(a.ai.close), paths: { ...a.ai.paths, close: move(a.ai.paths.close) }, issued_at: BAR_T + 64 },
  };
}

/** Two holding 1-minute lines closing in on the last candle: they meet in 6 candles. */
const LEVEL_MAP = {
  schema_version: 1, price: 5.36, rounds: null, intraday: [], five_minute: null, daily: [], daily_sessions: 0,
  daily_error: null, study: null,
  lines: {
    five_minute: [],
    one_minute: [
      { id: 'tl-s', home: 'one_minute', kind: 'support', dir: 'up', state: 'holding', touches: [{ t: et(14, 30), p: 5.0 }],
        t1: et(14, 30), p1: 5.0, t2: et(14, 50), p2: 5.2, now_t: BAR_T, now_p: 5.3, slope: 0.01, band: 0.01 },
      { id: 'tl-r', home: 'one_minute', kind: 'resistance', dir: 'down', state: 'holding',
        touches: [{ t: et(14, 30), p: 5.74 }], t1: et(14, 30), p1: 5.74, t2: et(14, 50), p2: 5.54, now_t: BAR_T,
        now_p: 5.42, slope: -0.01, band: 0.01 },
    ],
  },
};

async function openApus(page: Page, answer: unknown, status: unknown = statusWire) {
  const api = await mockLiveTraderApi(page, { bars: false, positions: [] });
  const one = minuteBars();
  // Only the 1-minute pane carries candles here; the other panes have none (Ahead draws on the 1-minute pane only).
  await page.route('**/api/ticker/APUS/bars*', async route => {
    const tf = new URL(route.request().url()).searchParams.get('timeframe') ?? '1Min';
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ bars: tf === '1Min' ? one : [], coverage: null }) });
  });
  await page.route('**/api/ticker/APUS', route => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify(e2eTickerDetail('APUS', 5.36, 2.29)) }));
  await page.route(/\/api\/stock-read\/APUS(\?.*)?$/, route => route.fulfill({ status: 200,
    contentType: 'application/json', body: JSON.stringify({ ...apusReadWire, level_map: LEVEL_MAP }) }));
  await page.route('**/api/ahead/forecast/APUS', route => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify(answer) }));
  await page.route('**/api/ahead/status', route => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify(status) }));
  await page.goto('/?view=stock&symbol=APUS');
  await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible({ timeout: 20_000 });
  return api;
}

/** The zone's main sentence, on the zone or at the pane's top right, whichever is showing. */
const shown = (page: Page, text: string) => page.getByText(text, { exact: true }).filter({ visible: true }).first();

const openSheet = (page: Page) => page.locator('[data-testid^="ahead-open-sheet"]').filter({ visible: true }).first()
  .click();

test.describe('Ahead on the 1-minute chart', () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test('is off by default, says why the AI view is hidden, and shows it with the exam once asked', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const asked: string[] = [];
    page.on('request', r => {
      if (r.url().includes('/api/ahead/')) asked.push(r.url());
    });
    const { mutations } = await openApus(page, readyAnswer());
    const toggle = page.getByTestId('ahead-toggle');
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await expect(toggle).toContainText('new');
    expect(asked).toEqual([]);

    await toggle.click();
    await expect(shown(page, AHEAD_WORDS.hiddenNotPassed)).toBeVisible({ timeout: 15_000 });
    await openSheet(page);
    await expect(page.getByTestId('ahead-sheet')).toBeVisible();
    await expect(page.getByTestId('ahead-walls-reason')).toHaveText(AHEAD_WORDS.hiddenNotPassed);
    await page.getByTestId('ahead-unearned').click();
    await expect(page.getByTestId('ahead-unearned')).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByTestId('ahead-volume-q50')).toHaveText('120k');
    await expect(page.getByTestId('ahead-exam-tag')).toHaveText('has not passed its exam');
    await shot(page, 'ahead-all');

    await page.getByTestId('ahead-scope-flat_top').click();
    await expect(page.getByTestId('ahead-trigger-card')).toBeVisible();
    await shot(page, 'ahead-flat-top');
    await page.getByTestId('ahead-scope-lines').click();
    await expect(page.getByTestId('ahead-lines-meet')).toContainText('lines meet ≈ 15:08');
    await page.getByTestId('ahead-sheet-close').click();
    await expect(page.getByTestId('ahead-sheet')).toHaveCount(0);
    if (SHOTS) {
      await openSheet(page);
      await page.getByTestId('ahead-scope-all').click();
      await page.getByTestId('ahead-sheet-close').click();
      await page.getByTestId('chart-grid-cell-1Min').getByRole('button', { name: 'Enter full screen' }).click();
      await page.waitForTimeout(1500);
      await shot(page, 'ahead-chart');
    }

    expect(mutations).toEqual([]);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test("still carries Nova's lines on to where they meet with no forecaster on the desk", async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openApus(page, { ...structuredClone(notSetUpWire), symbol: 'APUS', bar_t: BAR_T, as_of: BAR_T + 60,
      generated_at: BAR_T + 65 }, noStatusWire);
    await page.getByTestId('ahead-toggle').click();
    await expect(shown(page, AHEAD_WORDS.notSetUp('NOVA_AHEAD_URL is not set'))).toBeVisible({ timeout: 15_000 });
    await openSheet(page);
    await page.getByTestId('ahead-scope-lines').click();
    await expect(page.getByTestId('ahead-lines-meet')).toContainText('lines meet ≈ 15:08');
    await expect(page.getByTestId('ahead-exam-card')).toContainText(AHEAD_WORDS.noForecaster(noStatusWire.reason));
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
