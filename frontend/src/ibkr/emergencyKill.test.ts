import { beforeEach, describe, expect, it, vi } from 'vitest';

const cancelAllWorkingOrders = vi.fn();
const flattenAccount = vi.fn();
const patchBotSession = vi.fn();
const refreshBotSessionNow = vi.fn();
const lockTicketSession = vi.fn();

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
  lockTicketSession: (...args: unknown[]) => lockTicketSession(...args),
}));
const desk: { venue: string | null } = { venue: 'live' };
vi.mock('./confirmedDeskVenue', () => ({
  getConfirmedDeskVenueSnapshot: () => ({ venue: desk.venue, generation: null }),
}));

import { runEmergencyKill } from './emergencyKill';

describe('runEmergencyKill', () => {
  beforeEach(() => {
    desk.venue = 'live';
    cancelAllWorkingOrders.mockReset();
    flattenAccount.mockReset();
    patchBotSession.mockReset();
    refreshBotSessionNow.mockReset();
    lockTicketSession.mockReset();
    lockTicketSession.mockResolvedValue({ ok: true, code: null, message: null });
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
    lockTicketSession.mockImplementation(async () => {
      order.push('lock');
      return { ok: true, code: null, message: null };
    });

    const result = await runEmergencyKill();

    expect(result).toEqual({ ok: true, errors: [] });
    expect(order).toEqual([
      'lock',
      'autonomy:0',
      'cancel',
      'flatten',
      'lock',
    ]);
    expect(patchBotSession).toHaveBeenCalledOnce();
    expect(refreshBotSessionNow).toHaveBeenCalledOnce();
  });

  it('names the venue read at the click on both legs, even when the desk moves between them', async () => {
    cancelAllWorkingOrders.mockImplementation(async () => {
      desk.venue = 'paper'; // the pill clicked while the cancels ran
      return { ok: true, cancelled: [], failed: [], error: null };
    });

    await runEmergencyKill();

    expect(cancelAllWorkingOrders).toHaveBeenCalledWith(undefined, 'live');
    expect(flattenAccount).toHaveBeenCalledWith('live');
  });

  it('reads the venue before anything it runs can wait on the bot or the lock', async () => {
    patchBotSession.mockImplementation(async () => {
      desk.venue = 'sim'; // moved while the bot dropped to L0
      return { level: 0 };
    });

    await runEmergencyKill();

    expect(flattenAccount).toHaveBeenCalledWith('live');
  });

  it('names no venue before a status has said one, and still runs', async () => {
    desk.venue = null;

    const result = await runEmergencyKill();

    expect(cancelAllWorkingOrders).toHaveBeenCalledWith(undefined, null);
    expect(flattenAccount).toHaveBeenCalledWith(null);
    expect(result).toEqual({ ok: true, errors: [] });
  });

  it('shows what a stopped KILL says, and still drops to L0 and locks', async () => {
    const cancels = 'The desk moved from Live to Paper: the cancels stopped, none went to Paper.';
    const flatten = 'The desk moved from Live to Paper, so KILL stopped and sent nothing to Paper. '
      + 'Still open on Live: ABCD 100.';
    cancelAllWorkingOrders.mockResolvedValue({ ok: false, cancelled: [], failed: [], error: cancels });
    flattenAccount.mockResolvedValue({ ok: false, error: flatten });

    const result = await runEmergencyKill();

    expect(result).toEqual({ ok: false, errors: [cancels, flatten] });
    expect(patchBotSession).toHaveBeenCalledWith({ level: 0 });
    expect(lockTicketSession).toHaveBeenCalledTimes(2);
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
    expect(lockTicketSession).toHaveBeenCalledTimes(2);
  });

  it('still cancels and flattens when Bot Autonomy PATCH fails', async () => {
    patchBotSession.mockRejectedValue(new Error('Need Nova API key'));

    const result = await runEmergencyKill();

    expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
    expect(flattenAccount).toHaveBeenCalledOnce();
    expect(lockTicketSession).toHaveBeenCalledTimes(2);
    expect(result.ok).toBe(false);
    expect(result.errors).toContain('Need Nova API key');
    expect(patchBotSession).toHaveBeenCalledTimes(2);
  });

  it('never waits on the desk lock: a lock that hangs does not hold the cancel', async () => {
    lockTicketSession.mockImplementation(() => new Promise(() => {}));

    const result = await runEmergencyKill();

    expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
    expect(flattenAccount).toHaveBeenCalledOnce();
    expect(result).toEqual({ ok: true, errors: [] });
  });
});
