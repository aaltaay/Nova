import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('D-010 Trend Line two-click place', () => {
  test('armed Trendline accepts two clicks and does not require a drag', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();

    const card = page.locator('[data-testid^="ticker-chart-"]').first();
    await expect(card).toBeVisible();
    await expect.poll(async () => Number(await card.getAttribute('data-bar-count') ?? '0')).toBeGreaterThan(0);
    const chart = card.locator('.chart-body');

    const before = await chart.evaluate((el) => el.scrollLeft + el.clientWidth);
    await page.getByRole('button', { name: 'Use Trendline' }).click();
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'TrendLine');

    const box = await chart.boundingBox();
    expect(box).toBeTruthy();
    if (!box) return;
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.65);
    await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.35);

    await expect(chart).toHaveAttribute('data-drawing-count', '1');
    const after = await chart.evaluate((el) => el.scrollLeft + el.clientWidth);
    expect(after).toBe(before);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
