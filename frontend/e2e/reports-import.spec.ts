/**
 * Reports CSV/JSON import UI -- mocked journal API, no live IBKR.
 */
import { expect, test, type Page, type Route } from '@playwright/test';
import { JOURNAL_IMPORT_SAMPLE_CSV } from '../src/reports/importConstants';
import { attachErrorCollector } from './helpers/errorCollector';

function emptyYear(year: number) {
  return {
    year,
    timezone: 'America/New_York',
    includes_mock_data: false,
    year_pnl: 0,
    year_trade_count: 0,
    winning_days: 0,
    losing_days: 0,
    flat_days: 0,
    best_day: null,
    worst_day: null,
    months: Array.from({ length: 12 }, (_, i) => ({
      year,
      month: i + 1,
      pnl: 0,
      trade_count: 0,
      winning_days: 0,
      losing_days: 0,
      flat_days: 0,
      days: [],
    })),
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockReportsApis(page: Page, imported: { current: boolean }) {
  await page.route('**/api/journal/import', async route => {
    imported.current = true;
    await json(route, { ok: true, imported: 1, source: 'csv', skipped: 0, duplicates: 0 });
  });
  await page.route('**/api/journal/calendar**', route => {
    const year = Number(new URL(route.request().url()).searchParams.get('year') || '2026');
    const payload = emptyYear(year);
    if (imported.current) {
      payload.year_pnl = 48;
      payload.year_trade_count = 1;
      payload.winning_days = 1;
      payload.months[2] = {
        ...payload.months[2],
        pnl: 48,
        trade_count: 1,
        winning_days: 1,
      };
    }
    return json(route, payload);
  });
  await page.route('**/api/journal/tags**', route =>
    json(route, { includes_mock_data: false, count: 0, tags: [] }),
  );
  await page.route('**/api/journal/r-multiples**', route =>
    json(route, {
      includes_mock_data: false,
      trade_count: imported.current ? 1 : 0,
      scored_count: 0,
      skipped_no_stop: imported.current ? 1 : 0,
      expectancy_r: null,
      avg_win_r: null,
      avg_loss_r: null,
      trades: [],
    }),
  );
  await page.route('**/api/journal/drawdown**', route =>
    json(route, {
      includes_mock_data: false,
      trade_count: imported.current ? 1 : 0,
      final_equity: imported.current ? 48 : 0,
      peak_equity: imported.current ? 48 : 0,
      max_drawdown: 0,
      max_drawdown_pct: null,
      curve: [],
    }),
  );
}

test('Account Reports import control uploads a sample CSV', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  const imported = { current: false };
  await mockReportsApis(page, imported);
  await page.goto('/');
  await page.getByTestId('global-bar-account-nav').click();
  await page.getByRole('tab', { name: 'Reports' }).click();
  await expect(page.getByTestId('reports-import')).toBeVisible();
  await page.getByTestId('reports-import-input').setInputFiles({
    name: 'valid_trades.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(JOURNAL_IMPORT_SAMPLE_CSV),
  });
  await expect(page.getByText(/Imported 1 trade/)).toBeVisible();
  expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
});
