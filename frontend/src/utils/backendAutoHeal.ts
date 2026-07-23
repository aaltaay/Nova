/**
 * Auto-heal local API when the header diagnoses API_WEDGED / API_DOWN.
 * One attempt per browser session (dev / Electron only — prod web cannot spawn).
 */
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_WEDGED,
} from '../constants';
import { startLocalApi, type StartLocalApiResult } from './startLocalApi';

export const BACKEND_AUTO_HEAL_SESSION_KEY = 'nova:auto-heal:api';

const AUTO_HEAL_FLAGS = new Set<string>([
  BACKEND_DIAG_FLAG_WEDGED,
  BACKEND_DIAG_FLAG_DOWN,
]);

export function canAutoHealBackendFlag(flag: string | undefined | null): boolean {
  if (!flag) return false;
  return AUTO_HEAL_FLAGS.has(flag);
}

function healStorage(): Storage | null {
  try {
    return typeof sessionStorage !== 'undefined' ? sessionStorage : null;
  } catch {
    return null;
  }
}

/** True if this session still has an unused auto-heal slot. */
export function hasBackendAutoHealSlot(
  storage: Storage | null = healStorage(),
): boolean {
  if (!storage) return false;
  try {
    return !storage.getItem(BACKEND_AUTO_HEAL_SESSION_KEY);
  } catch {
    return false;
  }
}

export function markBackendAutoHealUsed(
  storage: Storage | null = healStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(BACKEND_AUTO_HEAL_SESSION_KEY, '1');
  } catch {
    // ignore
  }
}

export function clearBackendAutoHealSlot(
  storage: Storage | null = healStorage(),
): void {
  if (!storage) return;
  try {
    storage.removeItem(BACKEND_AUTO_HEAL_SESSION_KEY);
  } catch {
    // ignore
  }
}

/**
 * If flag is wedged/down and slot available, kill+restart local API once.
 * Returns null when skipped (wrong flag, slot used, or non-dev without Electron).
 */
export async function maybeAutoHealBackend(
  flag: string | undefined | null,
): Promise<StartLocalApiResult | null> {
  if (!canAutoHealBackendFlag(flag)) return null;
  if (!hasBackendAutoHealSlot()) return null;

  // Only environments that can actually restart a process.
  const desktop = typeof window !== 'undefined' ? window.novaDesktop : undefined;
  const canSpawn =
    (desktop?.isDesktop && typeof desktop.restartApi === 'function') ||
    Boolean(import.meta.env.DEV);
  if (!canSpawn) return null;

  markBackendAutoHealUsed();
  console.warn(`[Nova][API_AUTO_HEAL] ${flag} — restarting local API once`);
  return startLocalApi();
}
