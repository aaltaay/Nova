/**
 * Phase K -- sample Stock View Short side (fixtures only).
 * Does not place broker orders.
 */
import { expect, test } from '@playwright/test';

test.describe('sample shortability (Phase K)', () => {
  test('SMPL Stock View shows Short on Side for the sample margin desk', async ({
    page,
  }) => {
    await page.goto('/?view=sample&symbol=SMPL');

    await expect(page.getByText('Direction', { exact: true })).toHaveCount(0);
    const shortBtn = page.getByTestId('manual-order-side-short');
    await expect(shortBtn).toBeVisible();
    await expect(shortBtn).toBeEnabled();
    // No disabled-reason hint when sample shortability is green.
    await expect(page.getByTestId('manual-order-short-reason')).toHaveCount(0);

    await shortBtn.scrollIntoViewIfNeeded();
    await shortBtn.dispatchEvent('click');
    await expect(shortBtn).toHaveAttribute('aria-pressed', 'true', { timeout: 5_000 });
    await expect(page.getByTestId('manual-order-side-sell')).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });
});
