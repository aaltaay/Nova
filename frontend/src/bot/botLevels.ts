/**
 * The bot's levels (ADR 042), pure: the session's `level` is the master ceiling --
 * the most any setup may do on this venue -- and each setup with a scanner has its
 * own Off / Eyes / Strategy. What a setup may do now is the lower of the two
 * (`effective`). There is no chosen setup.
 */
import { BOT_LEVEL_LABELS, BOT_SETUP_LABELS } from '../constantGroups/bot';
import type { BotLevel, BotSession, BotSetupInfo } from './types';

export function clampLevel(n: unknown): BotLevel {
  const v = Number(n);
  if (!Number.isFinite(v) || v <= 0) return 0;
  return v >= 2 ? 2 : 1;
}

export function levelName(n: unknown): string {
  return BOT_LEVEL_LABELS[clampLevel(n)];
}

export function setupLabelOf(id: string): string {
  return BOT_SETUP_LABELS[id] ?? id.replace(/_/g, ' ');
}

function info(session: BotSession, id: string): BotSetupInfo | undefined {
  return (session.setups ?? []).find(s => s.id === id);
}

/** The master ceiling on this venue. */
export function masterLevel(session: BotSession | null | undefined): BotLevel {
  return clampLevel(session?.level ?? 0);
}

/** A setup's own switch; null for a setup without a scanner. */
export function ownLevel(session: BotSession, id: string): BotLevel | null {
  const row = info(session, id);
  if (row && !row.scanner) return null;
  const raw = row?.level ?? session.setup_levels?.[id];
  return raw == null ? (row ? 0 : null) : clampLevel(raw);
}

/** What the setup may do now: the backend's `effective`, else min(master, own). */
export function effectiveLevel(session: BotSession, id: string): BotLevel | null {
  const row = info(session, id);
  if (row && !row.scanner) return null;
  if (row?.effective != null) return clampLevel(row.effective);
  const own = ownLevel(session, id);
  return own == null ? null : (Math.min(own, masterLevel(session)) as BotLevel);
}

/** The setups that may be traded now (effective Strategy), in the session's order. */
export function strategySetups(session: BotSession | null | undefined): string[] {
  if (!session) return [];
  return (session.setups ?? []).filter(s => s.scanner && effectiveLevel(session, s.id) === 2).map(s => s.id);
}

/** The setups whose own switch is at Strategy, whatever the master says. */
export function ownStrategySetups(session: BotSession | null | undefined): string[] {
  if (!session) return [];
  return (session.setups ?? []).filter(s => s.scanner && ownLevel(session, s.id) === 2).map(s => s.id);
}

/** "First pullback, Bull flag" -- or "none". */
export function setupNames(ids: readonly string[]): string {
  return ids.length ? ids.map(setupLabelOf).join(', ') : 'none';
}

/** Activate is on: the backend's `active`, else its legacy alias. */
export function isActive(session: BotSession | null | undefined): boolean {
  if (!session) return false;
  return typeof session.active === 'boolean' ? session.active : session.armed === true;
}

/** The bot would trade a go trigger now: the backend's `ready`, else its legacy alias. */
export function isReady(session: BotSession | null | undefined): boolean {
  if (!session) return false;
  return typeof session.ready === 'boolean' ? session.ready : session.live_fire_ready === true;
}
