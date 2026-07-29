/**
 * Phase K — sample Stock View shortability chip + Short direction (fixtures only).
 * Does not place broker orders.
 */
import { expect, test } from '@playwright/test';

test.describe('sample shortability (Phase K)', () => {
  test('SMPL Stock View shows Short Available chip and Short direction is usable', async ({
    page,
  }) => {
    await page.goto('/?view=sample&symbol=SMPL');

    const chip = page.getByTestId('shortability-chip');
    await expect(chip).toBeVisible({ timeout: 15_000 });
    await expect(chip).toHaveAttribute('data-state', 'shortable_est');
    await expect(chip).toContainText(/Available/i);
    await expect(chip).toContainText(/250/);

    const shortBtn = page.getByTestId('manual-order-short-direction');
    await expect(shortBtn).toBeVisible();
    await expect(shortBtn).toBeEnabled();
    // No disabled-reason hint when sample shortability is green.
    await expect(page.getByTestId('manual-order-short-reason')).toHaveCount(0);

    await shortBtn.scrollIntoViewIfNeeded();
    await shortBtn.dispatchEvent('click');
    await expect(shortBtn).toHaveAttribute('aria-pressed', 'true', { timeout: 5_000 });
    await expect(
      page.locator('.manual-order-side button', { hasText: /^Sell$/ }),
    ).toHaveAttribute('aria-pressed', 'true');
  });
});
