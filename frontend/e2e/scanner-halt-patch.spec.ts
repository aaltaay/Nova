import { test, expect } from '@playwright/test';
import type { WebSocketRoute } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

// Socket and API are replayed browser facts; this never opens a real IB line.
test('a frozen row follows halt/resume/unknown while history keeps its own halt evidence', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  let scannerSocket: WebSocketRoute | undefined;
  await page.route('**/api/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
    dates: ['2026-09-23'], gappers: [{ symbol: 'PFSA', price: 4.3, halted: false }],
    gainers: [], losers: [], afterhours: [], large_cap: [], catalysts: [], table_state: 'frozen', last_scan: 100,
  }) }));
  await page.routeWebSocket('**/ws/scanner', socket => { scannerSocket = socket; });
  await page.goto('/e2e/fixtures/scannerHalt.html');
  const row = page.getByTestId('row-PFSA');
  await expect(row).toContainText('TRADING');
  await page.getByTestId('halted-chip').click();
  await expect(row).toHaveCount(0);
  await expect.poll(() => Boolean(scannerSocket)).toBe(true);
  scannerSocket!.send(JSON.stringify({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted: true }], ts: 200 }));
  await expect(row).toContainText('4.3 · HALTED');
  await expect(page.getByTestId('quote-age')).toHaveText('100');
  scannerSocket!.send(JSON.stringify({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted: null }], ts: 201 }));
  await expect(row).toContainText('UNKNOWN');
  scannerSocket!.send(JSON.stringify({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted: false }], ts: 202 }));
  await expect(row).toHaveCount(0);
  await page.getByTestId('halted-chip').click();
  await page.getByTestId('history').click();
  await expect(page.getByTestId('history-date')).toHaveText('2026-09-23');
  await expect(row).toContainText('TRADING');
  scannerSocket!.send(JSON.stringify({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted: true }], ts: 203 }));
  await expect(row).toContainText('TRADING');
  await page.getByTestId('live').click();
  await expect(page.getByTestId('history-date')).toHaveText('Live');
  await expect(row).toContainText('TRADING');
  await expect.poll(() => Boolean(scannerSocket)).toBe(true);
  scannerSocket!.send(JSON.stringify({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted: true }], ts: 204 }));
  await expect(row).toContainText('HALTED');
  expect(errors).toEqual([]);
});
