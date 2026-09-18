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

  it('locks and drops L0 first, then cancel, flatten, then lock again', async () => {
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
    expect(order).toEqual([
      'lock:false',
      'autonomy:0',
      'cancel',
      'flatten',
      'lock:false',
    ]);
    expect(patchBotSession).toHaveBeenCalledOnce();
    expect(refreshBotSessionNow).toHaveBeenCalledOnce();
  });

  it('reuses one in-flight compose when called twice', async () => {
    let resolveFlatten!: (value: { ok: boolean; error: null }) => void;
    flattenAccount.mockImplementation(
      () => new Promise((resolve) => {
        resolveFlatten = resolve;
      }),
    );

    const first = runEmergencyKill();
    const second = runEmergencyKill();
    await vi.waitFor(() => expect(flattenAccount).toHaveBeenCalledOnce());
    expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
    resolveFlatten({ ok: true, error: null });
    await expect(first).resolves.toEqual({ ok: true, errors: [] });
    await expect(second).resolves.toEqual({ ok: true, errors: [] });
    expect(flattenAccount).toHaveBeenCalledOnce();
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
    expect(patchBotSession).toHaveBeenCalledTimes(2);
  });
});
