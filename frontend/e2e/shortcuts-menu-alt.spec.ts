import { expect, test, type Page } from '@playwright/test';

async function preparePage(page: Page) {
  await page.goto('/');
  await page.evaluate(() => {
    localStorage.removeItem('nova.hotkeys.profile.v1');
    localStorage.removeItem('nova.hotkeys.menu-default-epoch');
  });
  await page.reload();
  await page.waitForSelector('#root', { timeout: 10000 });
  await page.waitForTimeout(500);
}

async function holdCtrlAlt(page: Page) {
  await page.keyboard.down('Control');
  await page.keyboard.down('Alt');
}

async function releaseCtrlAlt(page: Page) {
  await page.keyboard.up('Alt');
  await page.keyboard.up('Control');
}

test.describe('hold-Ctrl+Alt shortcuts menu', () => {
  test('opens peek on Ctrl+Alt and closes on release', async ({ page }) => {
    await preparePage(page);
    await page.locator('body').click({ position: { x: 8, y: 8 } });

    const binding = await page.evaluate(async () => {
      const mod = await import('/src/hotkeys/effectiveBindings.ts');
      const storage = await import('/src/hotkeys/hotkeyStorage.ts');
      return mod.getEffectiveMenuBinding(storage.loadProfile());
    });
    expect(binding).toEqual({ key: 'Alt', ctrl: true });

    await holdCtrlAlt(page);
    const open = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
    await expect(open).toBeVisible({ timeout: 2000 });

    await releaseCtrlAlt(page);
    await expect(open).toHaveCount(0, { timeout: 2000 });
  });

  test('opens while a text input is focused', async ({ page }) => {
    await preparePage(page);

    await page.evaluate(() => {
      const input = document.createElement('input');
      input.type = 'text';
      input.id = 'alt-menu-focus-probe';
      document.body.appendChild(input);
      input.focus();
    });
    await expect(page.locator('#alt-menu-focus-probe')).toBeFocused();

    await holdCtrlAlt(page);
    await expect(
      page.getByRole('dialog', { name: 'Keyboard shortcuts' }),
    ).toBeVisible({ timeout: 2000 });
    await releaseCtrlAlt(page);
  });

  test('epoch migration clears accidental letter override', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem(
        'nova.hotkeys.profile.v1',
        JSON.stringify({
          schemaVersion: 3,
          fileName: 'hotkey.htk',
          records: [],
          novaActions: [],
          shortcutsMenuKey: { label: 'A', key: 'a' },
          updatedAt: new Date().toISOString(),
        }),
      );
      localStorage.removeItem('nova.hotkeys.menu-default-epoch');
    });
    await page.reload();
    await page.waitForSelector('#root', { timeout: 10000 });
    await page.waitForTimeout(500);
    await page.locator('body').click({ position: { x: 8, y: 8 } });

    const key = await page.evaluate(async () => {
      const storage = await import('/src/hotkeys/hotkeyStorage.ts');
      return storage.loadProfile().shortcutsMenuKey ?? null;
    });
    expect(key).toBeNull();

    await holdCtrlAlt(page);
    await expect(
      page.getByRole('dialog', { name: 'Keyboard shortcuts' }),
    ).toBeVisible({ timeout: 2000 });
    await releaseCtrlAlt(page);
  });
});
