/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
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
  pinDialogOpen: false,
  onConfirmClose: () => {},
  onConfirmPlace: () => {},
  onPinSubmit: () => true,
  onPinClose: () => {},
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
  });

  it('disables Place when spending is locked', () => {
    const btn = render({ spendLocked: true });
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toBe('Orders locked');
  });

  it('shows the backend lock reason as the button title', () => {
    const btn = render({
      spendLocked: true,
      spendLockReason: 'live door but broker managedAccounts are paper',
    });
    expect(btn.title).toBe('live door but broker managedAccounts are paper');
  });

  it('shows the lock reason inline so the operator sees it without hovering', () => {
    render({ spendLocked: true, spendLockReason: 'Orders locked — reason here' });
    const note = container.querySelector('[data-testid="spend-lock-note"]');
    expect(note?.textContent).toBe('Orders locked — reason here');
  });

  it('keeps the PIN unlock affordance reachable while locked', () => {
    const btn = render({ spendLocked: true, needsPinUnlock: true });
    expect(btn.disabled).toBe(false);
  });

  it('still disables Place when disconnected', () => {
    const btn = render({ connected: false, spendLocked: false });
    expect(btn.disabled).toBe(true);
  });
});
