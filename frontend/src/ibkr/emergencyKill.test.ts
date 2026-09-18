import { beforeEach, describe, expect, it, vi } from 'vitest';

const cancelAllWorkingOrders = vi.fn();
const flattenAccount = vi.fn();
const patchBotSession = vi.fn();
const refreshBotSessionNow = vi.fn();
const writeTicketSessionUnlocked = vi.fn();

vi.mock('./placeOrder', () => ({
  cancelAllWorkingOrders: (...args: unknown[]) => cancelAllWorkingOrders(...args),
}));
vi.mock('./flattenAccount', () => ({
  flattenAccount: (...args: unknown[]) => flattenAccount(...args),
}));
vi.mock('../bot/api', () => ({
  patchBotSession: (...args: unknown[]) => patchBotSession(...args),
}));
vi.mock('../bot/botSessionPoller', () => ({
  refreshBotSessionNow: (...args: unknown[]) => refreshBotSessionNow(...args),
}));
vi.mock('./ticketUnlock', () => ({
  writeTicketSessionUnlocked: (...args: unknown[]) => writeTicketSessionUnlocked(...args),
}));

import { runEmergencyKill } from './emergencyKill';

describe('runEmergencyKill', () => {
  beforeEach(() => {
    cancelAllWorkingOrders.mockReset();
    flattenAccount.mockReset();
    patchBotSession.mockReset();
    refreshBotSessionNow.mockReset();
    writeTicketSessionUnlocked.mockReset();
    cancelAllWorkingOrders.mockResolvedValue({
      ok: true,
      cancelled: [1],
      failed: [],
      error: null,
    });
    flattenAccount.mockResolvedValue({ ok: true, error: null });
    patchBotSession.mockResolvedValue({ level: 0 });
  });

  it('invokes cancel, flatten, L0 PATCH, then desk lock in that order', async () => {
    const order: string[] = [];
    cancelAllWorkingOrders.mockImplementation(async () => {
      order.push('cancel');
      return { ok: true, cancelled: [], failed: [], error: null };
    });
    flattenAccount.mockImplementation(async () => {
      order.push('flatten');
      return { ok: true, error: null };
    });
    patchBotSession.mockImplementation(async (body: { level: number }) => {
      order.push(`autonomy:${body.level}`);
      return { level: 0 };
    });
    writeTicketSessionUnlocked.mockImplementation((unlocked: boolean) => {
      order.push(`lock:${unlocked}`);
    });

    const result = await runEmergencyKill();

    expect(result).toEqual({ ok: true, errors: [] });
    expect(order).toEqual(['cancel', 'flatten', 'autonomy:0', 'lock:false']);
    expect(refreshBotSessionNow).toHaveBeenCalledOnce();
  });

  it('still flattens, drops to L0, and locks when cancel-all fails', async () => {
    cancelAllWorkingOrders.mockResolvedValue({
      ok: false,
      cancelled: [],
      failed: [{ order_id: 9, error: 'busy' }],
      error: '1 cancel(s) failed',
    });

    const result = await runEmergencyKill();

    expect(result.ok).toBe(false);
    expect(result.errors).toContain('1 cancel(s) failed');
    expect(flattenAccount).toHaveBeenCalledOnce();
    expect(patchBotSession).toHaveBeenCalledWith({ level: 0 });
    expect(writeTicketSessionUnlocked).toHaveBeenCalledWith(false);
  });

  it('still cancels and flattens when Bot Autonomy PATCH fails', async () => {
    patchBotSession.mockRejectedValue(new Error('Need Nova API key'));

    const result = await runEmergencyKill();

    expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
    expect(flattenAccount).toHaveBeenCalledOnce();
    expect(writeTicketSessionUnlocked).toHaveBeenCalledWith(false);
    expect(result.ok).toBe(false);
    expect(result.errors).toContain('Need Nova API key');
  });
});
