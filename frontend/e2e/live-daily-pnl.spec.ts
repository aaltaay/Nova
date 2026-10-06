import { expect, test } from '@playwright/test';

const daily = "IBKR's daily P&L for the account; commissions are already included.";
const reset = 'IBKR owns the daily reset, configured in TWS; the API does not report its time.';

for (const scenario of [
  { name: 'overnight lifetime loss is excluded from the daily meter', pnl: 0,
    meter: { source: 'ibkr_daily_pnl', compares: daily, reset_semantics: reset,
      commissions: 2, commissions_in_figure: true, UnrealizedPnL: -250 },
    text: 'IBKR owns the daily reset' },
  { name: 'the summary fallback states its lifetime limitation and missing daily source', pnl: -250,
    meter: { source: 'account_summary', fallback: true, fallback_reason: 'Daily subscription pending',
      compares: 'Fallback includes lifetime unrealized P&L; commissions are already included.',
      reset_semantics: 'The summary has no daily-reset guarantee.', commissions: 2 },
    text: 'Daily subscription pending' },
  { name: 'unreadable commissions keep the known daily figure and state the entry hold', pnl: -40,
    meter: { source: 'ibkr_daily_pnl', compares: daily, reset_semantics: reset,
      commissions_unknown: true, commissions_error: 'Ledger unreadable' },
    text: 'new Live bot entries held' },
]) {
  test(scenario.name, async ({ page }) => {
    const mutations: string[] = [];
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://127.0.0.1:8999/**', async route => {
      if (route.request().method() !== 'GET') mutations.push(route.request().url());
      await route.fulfill({ json: { day_pnl: scenario.pnl, meter: scenario.meter } });
    });
    await page.goto('/e2e/fixtures/live-daily-pnl.html');
    const today = page.getByTestId('bots-breaker-today');
    await expect(today, `browser errors: ${errors.join('; ')}`).toContainText(Math.abs(scenario.pnl).toFixed(2));
    await expect(today).toHaveAttribute('data-tip', new RegExp(scenario.text));
    await today.hover();
    const tip = page.getByRole('tooltip');
    await expect(tip).toBeVisible();
    await expect(tip).toContainText(scenario.text);
    await expect(tip).not.toContainText('− commissions');
    expect(mutations).toEqual([]);
    expect(errors).toEqual([]);
  });
}
