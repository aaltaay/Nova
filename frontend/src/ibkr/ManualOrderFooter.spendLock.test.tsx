/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TICKET_WHY_SENDING, WHY_GATEWAY_NOT_CONNECTED } from '../constantGroups/trader_chrome';
import { ManualOrderFooter } from './ManualOrderFooter';

const BASE = {
  isPaper: true,
  needsPinUnlock: false,
  connected: true,
  submitting: false,
  spendLocked: false,
  quantityLocked: false,
  forcedQty: null,
  sessionUnlocked: true,
  result: null,
  confirmSummary: null,
  onConfirmClose: () => {},
  onConfirmPlace: () => {},
};

describe('ManualOrderFooter spend lock (D-013)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function render(props: Partial<typeof BASE> & { spendLockReason?: string | null }) {
    act(() => {
      root.render(<ManualOrderFooter {...BASE} {...props} />);
    });
    return container.querySelector('.manual-order-submit') as HTMLButtonElement;
  }

  it('enables Place when spending is armed', () => {
    const btn = render({ spendLocked: false });
    expect(btn.disabled).toBe(false);
    expect(btn.dataset.why).toBeUndefined();
    expect(btn.title).toMatch(/practice account/);
  });

  it('disables Place when spending is locked', () => {
    const btn = render({ spendLocked: true });
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toBe('Orders locked');
  });

  it('says the backend lock reason on the locked button, with no native title stacked on it', () => {
    const btn = render({
      spendLocked: true,
      spendLockReason: 'live door but broker managedAccounts are paper',
    });
    expect(btn.dataset.why).toBe('live door but broker managedAccounts are paper');
    expect(btn.hasAttribute('title')).toBe(false);
  });

  it('says why Place is locked while an order is in flight', () => {
    const btn = render({ submitting: true });
    expect(btn.disabled).toBe(true);
    expect(btn.dataset.why).toBe(TICKET_WHY_SENDING);
  });

  it('shows the lock reason inline so the operator sees it without hovering', () => {
    render({ spendLocked: true, spendLockReason: 'Orders locked — reason here' });
    const note = container.querySelector('[data-testid="spend-lock-note"]');
    expect(note?.textContent).toBe('Orders locked — reason here');
  });

  it('names the disarm on the button so the operator looks at the padlock, not Settings (ADR 018)', () => {
    const btn = render({
      spendLocked: true,
      spendDisarmed: true,
      spendLockReason: 'Desk is disarmed -- arm trading in this session before placing',
    });
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toBe('Desk disarmed — arm at the padlock');
    const note = container.querySelector('[data-testid="spend-lock-note"]');
    expect(note?.className).toContain('manual-order-lock-note--spend');
    expect(note?.textContent).toContain('arm trading in this session');
  });

  it('keeps the PIN unlock affordance reachable while locked', () => {
    const btn = render({ spendLocked: true, needsPinUnlock: true });
    expect(btn.disabled).toBe(false);
  });

  it('still disables Place when disconnected, and says the Gateway is why', () => {
    const btn = render({ connected: false, spendLocked: false });
    expect(btn.disabled).toBe(true);
    expect(btn.dataset.why).toBe(WHY_GATEWAY_NOT_CONNECTED);
  });
});
