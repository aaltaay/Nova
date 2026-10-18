import { expect, test, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

/**
 * #459: in a 320 px Trader rail the quote card's "Rel vol (Alpaca avg)" label
 * could not shrink, so its value took the ellipsis and 4.21 read "4.…". Every
 * stat -- Float, Vol, Rel vol, Gap%, High, Low -- keeps its whole value and its
 * whole label at every rail width the operator can drag to (320-720 px) and
 * at DPR 1 and 1.5, in the source fixture and on the full Trader route.
 */
const RAILS = [320, 360, 720];
const DPRS = [1, 1.5];
const LABELS = ['Float', 'Vol', 'Rel vol (Alpaca avg)', 'Gap%', 'High', 'Low'];

type Cell = { label: string; value: string; clipped: string[] };

/** Each stat cell: its texts, and which of its parts overflow their box or the cell. */
async function measureStats(page: Page): Promise<{ rail: number; cells: Cell[] }> {
  return page.evaluate(() => {
    const grid = document.querySelector('[data-testid="stock-view-quote-stats"]') as HTMLElement;
    const rail = document.querySelector('[data-testid="stock-view-rail"], .sv-rail') as HTMLElement;
    const within = (inner: DOMRect, outer: DOMRect) =>
      inner.left >= outer.left - 0.5 && inner.right <= outer.right + 0.5
      && inner.top >= outer.top - 0.5 && inner.bottom <= outer.bottom + 0.5;
    const cells = [...grid.querySelectorAll<HTMLElement>('.cq-cell')].map((cell) => {
      const label = cell.querySelector('.cq-label') as HTMLElement;
      const value = cell.querySelector('.cq-value') as HTMLElement;
      const clipped: string[] = [];
      for (const [name, el] of [['label', label], ['value', value]] as const) {
        if (el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight) clipped.push(`${name} overflows itself`);
        if (!within(el.getBoundingClientRect(), cell.getBoundingClientRect())) clipped.push(`${name} leaves the cell`);
      }
      if (!within(cell.getBoundingClientRect(), grid.getBoundingClientRect())) clipped.push('cell leaves the grid');
      return { label: label.textContent ?? '', value: value.textContent ?? '', clipped };
    });
    return { rail: rail.getBoundingClientRect().width, cells };
  });
}

function expectWhole(cells: Cell[]) {
  expect(cells.map((c) => c.label)).toEqual(LABELS);
  for (const cell of cells) {
    expect(cell.clipped, `${cell.label} = ${cell.value}`).toEqual([]);
    expect(cell.value).not.toMatch(/…/);
  }
}

for (const dpr of DPRS) {
  test.describe(`quote stats at DPR ${dpr}`, () => {
    test.use({ deviceScaleFactor: dpr });

    for (const rail of RAILS) {
      test(`the source fixture keeps every stat whole (${rail} px rail)`, async ({ page }) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto(`/e2e/fixtures/quote-rail-stats.html?rail=${rail}`);
        const relVol = page.getByTestId('stock-view-quote-stats').locator('.cq-cell', { hasText: 'Rel vol' });
        await expect(relVol.locator('.cq-value')).toHaveText('4.21');
        await expect(relVol).toHaveAttribute('title', /Alpaca daily-bar average/);
        const { rail: width, cells } = await measureStats(page);
        expect(Math.round(width)).toBe(rail);
        expectWhole(cells);
      });
    }

    test('the full Trader route keeps every stat whole at the rail\'s default, minimum and maximum', async ({ page }) => {
      const { errors } = attachErrorCollector(page);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto('/?view=sample&symbol=SMPL');
      const stats = page.getByTestId('stock-view-quote-stats');
      await expect(stats.locator('.cq-cell', { hasText: 'Rel vol' }).locator('.cq-value'))
        .toHaveText(/^\d+\.\d\d$/, { timeout: 30_000 });
      await expect.poll(async () => Math.round((await measureStats(page)).rail)).toBe(360);
      expectWhole((await measureStats(page)).cells);
      const handle = page.getByRole('separator', { name: 'Resize trading rail' });
      for (const [dx, rail] of [[300, 320], [-600, 720]] as const) {
        const box = (await handle.boundingBox())!;
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width / 2 + dx, box.y + box.height / 2, { steps: 5 });
        await page.mouse.up();
        await expect.poll(async () => Math.round((await measureStats(page)).rail)).toBe(rail);
        expectWhole((await measureStats(page)).cells);
      }
      expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
    });
  });
}
