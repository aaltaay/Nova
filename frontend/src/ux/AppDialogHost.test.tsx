/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { alertApp, confirmApp, promptApp } from './appDialogApi';
import { AppDialogHost } from './AppDialogHost';

describe('AppDialogHost global UX', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <AppDialogHost>
          <div data-testid="child">child</div>
        </AppDialogHost>,
      );
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('confirmApp resolves true on Confirm and false on Cancel', async () => {
    let result: boolean | undefined;
    act(() => {
      void confirmApp({
        title: 'Switch to Live Gateway',
        message: 'Requires live Gateway on 4001.',
        confirmLabel: 'Switch',
        tone: 'danger',
      }).then(v => {
        result = v;
      });
    });

    // Radix portals into document.body, not the React root container.
    expect(document.querySelector('[data-testid="app-dialog"]')).toBeTruthy();
    expect(document.querySelector('[data-testid="app-dialog-title"]')?.textContent).toBe(
      'Switch to Live Gateway',
    );
    expect(document.querySelector('[data-tone="danger"]')).toBeTruthy();

    await act(async () => {
      (document.querySelector('[data-testid="app-dialog-confirm"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(result).toBe(true);

    act(() => {
      void confirmApp('second').then(v => {
        result = v;
      });
    });
    await act(async () => {
      (document.querySelector('[data-testid="app-dialog-cancel"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(result).toBe(false);
  });

  it('alertApp resolves after OK', async () => {
    let done = false;
    act(() => {
      void alertApp({ title: 'Notice', message: 'Something happened' }).then(() => {
        done = true;
      });
    });
    expect(document.querySelector('[data-testid="app-dialog-ok"]')).toBeTruthy();
    await act(async () => {
      (document.querySelector('[data-testid="app-dialog-ok"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(done).toBe(true);
  });

  it('promptApp Cancel returns null; Confirm stays disabled until expectedValue matches', async () => {
    let typed: string | null | undefined = 'unset';
    act(() => {
      void promptApp({
        title: 'Flatten',
        message: 'Type FLATTEN',
        expectedValue: 'FLATTEN',
        tone: 'danger',
      }).then(v => {
        typed = v;
      });
    });

    const confirmBtn = document.querySelector(
      '[data-testid="app-dialog-confirm"]',
    ) as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);

    await act(async () => {
      (document.querySelector('[data-testid="app-dialog-cancel"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(typed).toBeNull();
  });
});
