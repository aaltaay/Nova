/**
 * Phase K -- sample Stock View Short side (fixtures only).
 * Does not place broker orders.
 *
 * The sample desk is a Paper desk, and both practice venues refuse every short
 * entry (`PRACTICE_NO_SHORTS`, AGENTS.md section 3): the Short segment is shown
 * for the margin account but locked, with Nova's reason rather than the
 * symbol's (ibkr/shortDisabledReason.ts, QA V13).
 */
import { expect, test } from '@playwright/test';
import { PRACTICE_NO_SHORTS_REASON } from '../src/constantGroups/practice';

const ARTIFACTS = '/opt/cursor/artifacts';

test.describe('sample shortability (Phase K)', () => {
  test('SMPL Stock View shows Short on Side, locked with the practice reason', async ({
    page,
  }) => {
    // The sample status is an armed Paper desk, so the ticket shows Place without an unlock.
    await page.goto('/?view=sample&symbol=SMPL');

    await expect(page.getByText('Direction', { exact: true })).toHaveCount(0);
    const shortBtn = page.getByTestId('manual-order-side-short');
    await expect(shortBtn).toBeVisible();
    await expect(shortBtn).toBeDisabled();
    // A locked control says why (ux/whyTip.ts), and the ticket prints it too.
    await expect(shortBtn).toHaveAttribute('data-why', PRACTICE_NO_SHORTS_REASON);
    await expect(page.getByTestId('manual-order-short-reason')).toHaveText(
      PRACTICE_NO_SHORTS_REASON,
    );

    const ticket = page.locator('form.manual-order-ticket').first();
    await ticket.scrollIntoViewIfNeeded();
    await expect(page.getByTestId('manual-order-submit')).toHaveText('Buy SMPL');
    const eh = page.getByTestId('manual-order-extended');
    await expect(eh).toBeVisible();
    await expect(eh).toBeChecked();
    await expect(eh).toBeEnabled();
    await expect(page.locator('#manual-order-hours')).toHaveCount(0);
    await ticket.screenshot({ path: `${ARTIFACTS}/ticket-side-margin-buy.png` });

    // Pressing the locked segment changes nothing: the ticket stays a Buy.
    await shortBtn.scrollIntoViewIfNeeded();
    await shortBtn.click({ force: true });
    await expect(shortBtn).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByTestId('manual-order-side-buy')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByTestId('manual-order-submit')).toHaveText('Buy SMPL');
    await ticket.screenshot({ path: `${ARTIFACTS}/ticket-side-margin-short-locked.png` });
  });
});
