/**
 * Pure desk policy -- role, close-after-give, first-host claim (ADR 011).
 */

import { TRADER_LAST_HOST_KEY } from '../../constantGroups/trader_view';
import type { TraderDeskRole } from './protocol';

export const TRADER_DOCK_CLAIM_KEY = 'nova.trader.dockClaim';

export type CloseAfterGive = 'close-window' | 'leave-scanner' | 'keep';

export function deskRoleFromStockView(urlSymbol: string | null): TraderDeskRole {
  return urlSymbol ? 'float' : 'host';
}

/** Pop out is a host-only extract. A float is already its own OS window. */
export function canExtractFromDesk(role: TraderDeskRole): boolean {
  return role === 'host';
}

export function closePolicyAfterGive(role: TraderDeskRole, remainingTabs: number): CloseAfterGive {
  if (remainingTabs > 0) return 'keep';
  return role === 'float' ? 'close-window' : 'leave-scanner';
}

export function isForeignTabDrag(sourceWindowId: string, thisWindowId: string): boolean {
  return Boolean(sourceWindowId) && sourceWindowId !== thisWindowId;
}

export function rememberLastHostWindow(
  storage: Pick<Storage, 'setItem'>,
  windowId: string,
): void {
  if (!windowId) return;
  storage.setItem(TRADER_LAST_HOST_KEY, windowId);
}

export function readLastHostWindow(storage: Pick<Storage, 'getItem'>): string | null {
  try {
    const value = storage.getItem(TRADER_LAST_HOST_KEY);
    return value || null;
  } catch {
    return null;
  }
}

export function shouldHandleDockRequest(args: {
  role: TraderDeskRole;
  sourceWindowId: string;
  thisWindowId: string;
  targetWindowId?: string;
}): boolean {
  if (args.role !== 'host') return false;
  if (!args.sourceWindowId || args.sourceWindowId === args.thisWindowId) return false;
  if (args.targetWindowId && args.targetWindowId !== args.thisWindowId) return false;
  return true;
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
