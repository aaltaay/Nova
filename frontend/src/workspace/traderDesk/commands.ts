/**
 * Pure desk policy -- role, close-after-give, first-host claim (ADR 011).
 */

import type { TraderDeskRole } from './protocol';

export const TRADER_DOCK_CLAIM_KEY = 'nova.trader.dockClaim';

export type CloseAfterGive = 'close-window' | 'leave-scanner' | 'keep';

export function deskRoleFromStockView(urlSymbol: string | null): TraderDeskRole {
  return urlSymbol ? 'float' : 'host';
}

export function closePolicyAfterGive(role: TraderDeskRole, remainingTabs: number): CloseAfterGive {
  if (remainingTabs > 0) return 'keep';
  return role === 'float' ? 'close-window' : 'leave-scanner';
}

export function isForeignTabDrag(sourceWindowId: string, thisWindowId: string): boolean {
  return Boolean(sourceWindowId) && sourceWindowId !== thisWindowId;
}

export function claimDockTarget(
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  requestId: string,
  windowId: string,
  now = Date.now(),
): boolean {
  let prev: { requestId?: string; windowId?: string } = {};
  try {
    prev = JSON.parse(storage.getItem(TRADER_DOCK_CLAIM_KEY) || '{}') as typeof prev;
  } catch {
    prev = {};
  }
  if (prev.requestId === requestId) return prev.windowId === windowId;
  storage.setItem(
    TRADER_DOCK_CLAIM_KEY,
    JSON.stringify({ requestId, windowId, ts: now }),
  );
  try {
    const check = JSON.parse(storage.getItem(TRADER_DOCK_CLAIM_KEY) || '{}') as typeof prev;
    return check.requestId === requestId && check.windowId === windowId;
  } catch {
    return false;
  }
}
