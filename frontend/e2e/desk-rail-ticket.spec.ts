import { expect, test } from '@playwright/test';

/**
 * #459: in the Desk's 320 px Trader rail the compact ticket header
 * (TRADE · SYM · SIM · <state> · fills EST | TIF DAY GTC) needed about 324 px
 * in about 306, so "GTC" ended 16 px past the rail's edge. The TIF control
 * must never clip, whichever state word the Sim venue tag carries, and the
 * venue tag keeps its `fills EST`.
 */
const CLOCKS = {
  replay: { sim: true, paused: true, replay_source: 'capture', replay_symbol: 'BRK/B', replay_date: '2026-09-22' },
  'live edge': { sim: true, paused: false, live_edge: true },
  'no replay': { sim: true, paused: true, replay_source: 'none' },
} as const;

/** 1440: the Desk caps the rail at 320 px (desk/desk.css); 1920: the rail's own 360 px. */
const VIEWPORTS = [
  { width: 1440, rail: 320 },
  { width: 1920, rail: 360 },
];

/** The longest symbol the desk takes, beside each state word. */
const SYMBOL = 'BRK/B';

for (const viewport of VIEWPORTS) {
  for (const [state, clock] of Object.entries(CLOCKS)) {
    test(`the rail keeps the ticket's TIF inside the card (${viewport.width} px, SIM · ${state})`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: 900 });
      await page.route('http://127.0.0.1:8999/**', async route => {
        const path = new URL(route.request().url()).pathname;
        let body: unknown = {};
        if (path === '/api/ibkr/status') {
          body = { enabled: true, connected: true, transport_connected: true, mode: 'sim', venue: 'sim', spend_status: 'paper_armed' };
        } else if (path === '/api/sim/clock') {
          body = clock;
        }
        await route.fulfill({ json: body });
      });
      await page.goto(`/e2e/fixtures/desk-rail-ticket.html?symbol=${encodeURIComponent(SYMBOL)}`);
      const tag = page.getByTestId('manual-order-header').getByTestId('stock-view-venue-tag');
      await expect(tag).toContainText(state);
      await expect(tag).toContainText('fills');
      const box = await page.evaluate(() => {
        const header = document.querySelector('[data-testid="manual-order-header"]') as HTMLElement;
        const rail = document.querySelector('[data-testid="stock-view-rail"]') as HTMLElement;
        const r = (el: Element) => el.getBoundingClientRect();
        const parts = ['manual-order-tif-day', 'manual-order-tif-gtc', 'stock-view-venue-tag', 'est-chip']
          .map((id) => r(header.querySelector(`[data-testid="${id}"]`)!));
        return {
          rail: r(rail).width,
          left: r(header).left,
          right: r(header).right,
          scroll: header.scrollWidth,
          client: header.clientWidth,
          parts: parts.map((b) => ({ left: b.left, right: b.right })),
        };
      });
      expect(box.rail).toBeLessThanOrEqual(viewport.rail);
      // Nothing in the header overflows it: both TIF buttons, the venue tag and its EST chip sit inside.
      expect(box.scroll).toBeLessThanOrEqual(box.client);
      for (const part of box.parts) {
        expect(part.left).toBeGreaterThanOrEqual(box.left);
        expect(part.right).toBeLessThanOrEqual(box.right);
      }
    });
  }
}
