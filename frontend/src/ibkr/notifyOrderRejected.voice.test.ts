import { beforeEach, describe, expect, it, vi } from 'vitest';

const { speakDesk, alertApp } = vi.hoisted(() => ({
  speakDesk: vi.fn(),
  alertApp: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../sound', () => ({ speakDesk }));
vi.mock('../ux', () => ({ alertApp, confirmApp: vi.fn() }));

import { notifyOrderRejected } from './notifyOrderRejected';

describe('notifyOrderRejected voice', () => {
  beforeEach(() => {
    speakDesk.mockClear();
    alertApp.mockClear();
  });

  it('says "Order rejected." beside the pop-up', async () => {
    await notifyOrderRejected({ message: 'estimated notional 596.54 exceeds BuyingPower 552.79' });
    expect(speakDesk).toHaveBeenCalledWith('Order rejected.');
    expect(alertApp).toHaveBeenCalledTimes(1);
  });

  it('stays silent for the soft warnings it never pops up', async () => {
    await notifyOrderRejected({ message: "Warning 2109: Attribute 'outsideRth' ignored" });
    await notifyOrderRejected({ message: '   ' });
    expect(speakDesk).not.toHaveBeenCalled();
  });
});
