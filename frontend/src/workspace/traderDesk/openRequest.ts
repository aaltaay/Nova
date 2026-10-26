/**
 * Ask the desk to open a symbol in its Trader, from a window that is not a desk (ADR 011 amendment,
 * 2026-10-26: the Top 9 pop-up). The host answers with the same `openStockView` a ticker click
 * runs, so the preview-tab rule and the live Level 2 cap (TRADER_MAX_LIVE_TABS) apply unchanged;
 * the asking window never holds Trader tabs of its own.
 *
 * Resolves true when a host opened it, false when none answered in time.
 */
import { createTraderDeskBus, type TraderDeskBus } from './bus';
import { readLastHostWindow } from './commands';
import { traderDeskMessage } from './protocol';

function newId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** One id per asking window: the host replies to it. */
const askerId = newId('ask');

export function requestOpenOnDesk(
  symbol: string,
  opts: { from?: string; waitMs: number; bus?: TraderDeskBus },
): Promise<boolean> {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return Promise.resolve(false);
  const bus = opts.bus ?? createTraderDeskBus();
  const owned = !opts.bus;
  const requestId = newId('open');
  let targetWindowId: string | undefined;
  try {
    targetWindowId = readLastHostWindow(localStorage) ?? undefined;
  } catch {
    targetWindowId = undefined;
  }
  return new Promise<boolean>((resolve) => {
    let done = false;
    const finish = (ok: boolean) => {
      if (done) return;
      done = true;
      unsub();
      window.clearTimeout(timer);
      if (owned) bus.close();
      resolve(ok);
    };
    const unsub = bus.subscribe((msg) => {
      if (msg.type === 'opened' && msg.requestId === requestId && msg.sourceWindowId === askerId) finish(true);
    });
    const timer = window.setTimeout(() => finish(false), opts.waitMs);
    bus.publish(traderDeskMessage('open-request', {
      symbol: sym,
      sourceWindowId: askerId,
      requestId,
      ...(targetWindowId ? { targetWindowId } : {}),
      ...(opts.from ? { from: opts.from } : {}),
    }));
  });
}
