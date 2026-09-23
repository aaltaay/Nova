/**
 * Phase K -- sample Stock View Short side (fixtures only).
 * Does not place broker orders.
 */
import { expect, test } from '@playwright/test';

const ARTIFACTS = '/opt/cursor/artifacts';

test.describe('sample shortability (Phase K)', () => {
  test('SMPL Stock View shows Short on Side for the sample margin desk', async ({
    page,
  }) => {
    // The sample status is an armed Paper desk, so the ticket shows Place without an unlock.
    await page.goto('/?view=sample&symbol=SMPL');

    await expect(page.getByText('Direction', { exact: true })).toHaveCount(0);
    const shortBtn = page.getByTestId('manual-order-side-short');
    await expect(shortBtn).toBeVisible();
    await expect(shortBtn).toBeEnabled();
    // No disabled-reason hint when sample shortability is green.
    await expect(page.getByTestId('manual-order-short-reason')).toHaveCount(0);

    const ticket = page.locator('form.manual-order-ticket').first();
    await ticket.scrollIntoViewIfNeeded();
    await expect(page.getByTestId('manual-order-submit')).toHaveText('Buy SMPL');
    const eh = page.getByTestId('manual-order-extended');
    await expect(eh).toBeVisible();
    await expect(eh).toBeChecked();
    await expect(eh).toBeEnabled();
    await expect(page.locator('#manual-order-hours')).toHaveCount(0);
    await ticket.screenshot({ path: `${ARTIFACTS}/ticket-side-margin-buy.png` });

    await shortBtn.scrollIntoViewIfNeeded();
    await shortBtn.dispatchEvent('click');
    await expect(shortBtn).toHaveAttribute('aria-pressed', 'true', { timeout: 5_000 });
    await expect(page.getByTestId('manual-order-side-sell')).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    await expect(page.getByTestId('manual-order-submit')).toHaveText('Short SMPL');
    await ticket.screenshot({ path: `${ARTIFACTS}/ticket-side-margin-short.png` });
  });
});
