/**
 * Phase K -- sample Stock View Short direction (fixtures only).
 * Does not place broker orders.
 */
import { expect, test } from '@playwright/test';

test.describe('sample shortability (Phase K)', () => {
  test('SMPL Stock View makes the verified Short direction usable', async ({
    page,
  }) => {
    await page.goto('/?view=sample&symbol=SMPL');

    const shortBtn = page.getByRole('button', { name: 'Short', exact: true });
    await expect(shortBtn).toBeVisible();
    await expect(shortBtn).toBeEnabled();
    // No disabled-reason hint when sample shortability is green.
    await expect(page.getByTestId('manual-order-short-reason')).toHaveCount(0);

    await shortBtn.scrollIntoViewIfNeeded();
    await shortBtn.dispatchEvent('click');
    await expect(shortBtn).toHaveAttribute('aria-pressed', 'true', { timeout: 5_000 });
    await expect(
      page.getByRole('button', { name: 'Sell', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true');
  });
});
