import { expect, test } from '@playwright/test';

/**
 * #459 (QA D13): at 1600 px or narrower the Desk board is 480 px wide, and its
 * footer -- `N of M`, "board freezes at the open" on Gappers, the exchange
 * filter's note and the dots legend -- held about 577 px in about 484 with
 * `overflow: hidden`, so the legend was cut off at the edge. Nothing in the
 * footer may sit outside it, at either board width.
 */
const CASES = [
  { viewport: 1440, list: 'gappers', hidden: false },
  { viewport: 1440, list: 'gappers', hidden: true },
  { viewport: 1440, list: 'gainers', hidden: false },
  { viewport: 1920, list: 'gappers', hidden: true },
];

for (const c of CASES) {
  test(`the Desk board footer shows all of itself (${c.viewport} px, ${c.list}${c.hidden ? ', filter hides a row' : ''})`, async ({ page }) => {
    await page.setViewportSize({ width: c.viewport, height: 900 });
    await page.route('http://127.0.0.1:8999/**', (route) => route.fulfill({ json: {} }));
    await page.goto(`/e2e/fixtures/desk-board-foot.html?list=${c.list}${c.hidden ? '&hidden=1' : ''}`);
    const foot = page.getByTestId('desk-board-foot');
    await expect(foot).toContainText(c.hidden ? '2 of 3' : '3 of 3');
    const box = await foot.evaluate((el) => {
      const r = (node: Element) => node.getBoundingClientRect();
      const outer = r(el);
      // Every visible piece of text or dot in the footer.
      const parts = Array.from(el.querySelectorAll('*'))
        .filter((node) => (node as HTMLElement).offsetParent !== null && r(node).width > 0)
        .map((node) => ({ cls: (node as HTMLElement).className, left: r(node).left, right: r(node).right }));
      return {
        left: outer.left,
        right: outer.right,
        scroll: el.scrollWidth,
        client: el.clientWidth,
        titles: Array.from(el.querySelectorAll('.desk-board__legend-item')).map((node) => node.getAttribute('title')),
        parts,
      };
    });
    expect(box.scroll).toBeLessThanOrEqual(box.client);
    for (const part of box.parts) {
      expect(part.left, part.cls).toBeGreaterThanOrEqual(box.left);
      expect(part.right, part.cls).toBeLessThanOrEqual(box.right);
    }
    // A short label never loses the meaning: each item's title names it in full.
    expect(box.titles).toEqual(['recording', 'allowlisted, depth line held', 'allowlisted, quiet']);
  });
}
