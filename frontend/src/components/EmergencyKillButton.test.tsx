/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  APP_DIALOG_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_TITLE,
  GLOBAL_BAR_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_HINT,
  GLOBAL_BAR_EMERGENCY_KILL_OPS,
} from '../constants';
import { EmergencyKillButton, EmergencyKillCard } from './EmergencyKillButton';

const confirmApp = vi.fn();
const alertApp = vi.fn();
const runEmergencyKill = vi.fn();

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmApp(...args),
  alertApp: (...args: unknown[]) => alertApp(...args),
}));

vi.mock('../ibkr/emergencyKill', () => ({
  runEmergencyKill: (...args: unknown[]) => runEmergencyKill(...args),
}));

describe('EmergencyKillButton', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    confirmApp.mockReset().mockResolvedValue(true);
    alertApp.mockReset().mockResolvedValue(undefined);
    runEmergencyKill.mockReset().mockResolvedValue({ ok: true, errors: [] });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<EmergencyKillButton />);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('is a red stop sign labelled Emergency KILL, with no native title to double the card', () => {
    const button = container.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.getAttribute('aria-label')).toBe(GLOBAL_BAR_EMERGENCY_KILL_LABEL);
    expect(button.textContent).toBe(GLOBAL_BAR_EMERGENCY_KILL_LABEL);
    expect(button.querySelector('[data-testid="stop-sign-icon"]')).toBeTruthy();
    expect(button.hasAttribute('title')).toBe(false);
    expect(button.className).toContain('global-app-bar__emergency-kill');
  });

  it('opens a card on focus that lists all four operations and says a click confirms first', async () => {
    const button = container.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    await act(async () => {
      button.focus();
      await Promise.resolve();
    });
    const card = document.body.querySelector('[data-testid="global-bar-emergency-kill-card"]');
    expect(card).toBeTruthy();
    for (const op of GLOBAL_BAR_EMERGENCY_KILL_OPS) {
      expect(card!.textContent).toContain(op);
    }
    expect(card!.textContent).toContain(GLOBAL_BAR_EMERGENCY_KILL_HINT);
  });

  it('the card names the running state while KILL runs', () => {
    const host = document.createElement('div');
    const cardRoot = createRoot(host);
    act(() => {
      cardRoot.render(<EmergencyKillCard busy />);
    });
    expect(host.textContent).toMatch(/KILL running/);
    act(() => {
      cardRoot.unmount();
    });
  });

  it('confirms then runs the existing-door compose helper', async () => {
    const button = container.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    await act(async () => {
      button.click();
      await Promise.resolve();
    });
    expect(confirmApp).toHaveBeenCalledWith(
      expect.objectContaining({
        title: GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_TITLE,
        confirmLabel: APP_DIALOG_EMERGENCY_KILL_LABEL,
        tone: 'danger',
      }),
    );
    expect(runEmergencyKill).toHaveBeenCalledOnce();
  });

  it('does not fire when the confirm dialog is cancelled', async () => {
    confirmApp.mockResolvedValue(false);
    const button = container.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    await act(async () => {
      button.click();
      await Promise.resolve();
    });
    expect(runEmergencyKill).not.toHaveBeenCalled();
  });

  it('opens only one confirm dialog for two rapid clicks', async () => {
    let resolveConfirm!: (value: boolean) => void;
    confirmApp.mockImplementation(
      () => new Promise<boolean>((resolve) => {
        resolveConfirm = resolve;
      }),
    );
    const button = container.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    await act(async () => {
      button.click();
      button.click();
      await Promise.resolve();
    });
    expect(confirmApp).toHaveBeenCalledOnce();
    await act(async () => {
      resolveConfirm(true);
      await Promise.resolve();
    });
    expect(runEmergencyKill).toHaveBeenCalledOnce();
  });
});
