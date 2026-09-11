import type { ConsoleMessage, Page } from '@playwright/test';

const EXPECTED_OFFLINE_CONSOLE_ERROR =
  /Failed to load resource|net::ERR_|WebSocket|Scanner API network error|HOD Momo config load failed|HOD blocklist fetch failed|closed orders fetch failed/i;

/** Capture real browser failures while CI intentionally runs without Nova API. */
export function attachErrorCollector(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on('pageerror', (error) => {
    errors.push(`pageerror: ${error.message}`);
  });
  page.on('console', (message: ConsoleMessage) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (EXPECTED_OFFLINE_CONSOLE_ERROR.test(text)) return;
    errors.push(`console.error: ${text}`);
  });
  return { errors };
}
