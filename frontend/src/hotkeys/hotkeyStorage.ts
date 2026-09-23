/**
 * Local-first hotkey profile persistence. Never sent to the backend.
 */

import {
  HOTKEY_PROFILE_SCHEMA_VERSION,
  type HotkeyKeyChord,
  type HotkeyProfile,
  type HotkeyRecord,
} from './types';
import { createDefaultNovaActions } from './novaActionDefaults';
import type { NovaActionRecord } from './novaActionTypes';
import {
  DESK_ASK_BID_HOTKEY_EPOCH,
  DESK_ASK_BID_HOTKEY_EPOCH_KEY,
  NOVA_ACTION_KINDS,
  SHORTCUTS_MENU_DEFAULT_EPOCH,
  SHORTCUTS_MENU_EPOCH_STORAGE_KEY,
  type NovaActionKind,
} from '../constants';

export const HOTKEY_STORAGE_KEY = 'nova.hotkeys.profile.v1';

export function createEmptyProfile(fileName = 'hotkey.htk'): HotkeyProfile {
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName,
    records: [],
    novaActions: createDefaultNovaActions(),
    updatedAt: new Date().toISOString(),
  };
}

export function profileFromRecords(
  records: HotkeyRecord[],
  fileName: string,
  novaActions?: NovaActionRecord[],
  extras?: Pick<HotkeyProfile, 'shortcutsMenuKey'>,
): HotkeyProfile {
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName,
    records,
    novaActions: novaActions ?? createDefaultNovaActions(),
    shortcutsMenuKey: extras?.shortcutsMenuKey,
    updatedAt: new Date().toISOString(),
  };
}

function isRecord(value: unknown): value is HotkeyRecord {
  if (!value || typeof value !== 'object') return false;
  const r = value as HotkeyRecord;
  return (
    typeof r.id === 'string'
    && typeof r.name === 'string'
    && typeof r.command === 'string'
    && r.key != null
    && typeof r.key === 'object'
  );
}

function isNovaAction(value: unknown): value is NovaActionRecord {
  if (!value || typeof value !== 'object') return false;
  const a = value as NovaActionRecord;
  return (
    typeof a.id === 'string'
    && typeof a.name === 'string'
    && NOVA_ACTION_KINDS.includes(a.kind as NovaActionKind)
    && a.key != null
    && typeof a.key === 'object'
    && typeof a.enabled === 'boolean'
    && typeof a.showButton === 'boolean'
    && a.params != null
    && typeof a.params === 'object'
  );
}

function isKeyChord(value: unknown): value is HotkeyKeyChord {
  if (!value || typeof value !== 'object') return false;
  const c = value as HotkeyKeyChord;
  return typeof c.key === 'string' && typeof c.label === 'string';
}

/**
 * Ensure newly shipped default Nova Actions appear on older local profiles.
 * Merge by id only so multiple defaults of the same kind (e.g. 100/50/25% Ask)
 * all land; never overwrite a user-edited row with the same id.
 */
export function mergeMissingDefaultNovaActions(
  existing: NovaActionRecord[],
  removedIds: Iterable<string> = [],
): NovaActionRecord[] {
  const removed = new Set(removedIds);
  const defaults = createDefaultNovaActions();
  const byId = new Set(existing.map((a) => a.id));
  const merged = existing.filter((a) => !removed.has(a.id));
  for (const def of defaults) {
    if (removed.has(def.id) || byId.has(def.id)) continue;
    merged.push(def);
    byId.add(def.id);
  }
  return merged;
}

function parseRemovedIds(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((id): id is string => typeof id === 'string' && id.length > 0);
}

/** Drop a Nova Action and remember the id so defaults do not revive on load. */
export function deleteNovaActionFromProfile(
  profile: HotkeyProfile,
  id: string,
): HotkeyProfile {
  const removed = new Set(profile.removedNovaActionIds ?? []);
  removed.add(id);
  return {
    ...profile,
    novaActions: profile.novaActions.filter((a) => a.id !== id),
    removedNovaActionIds: [...removed],
    updatedAt: new Date().toISOString(),
  };
}

export function upsertNovaActionInProfile(
  profile: HotkeyProfile,
  draft: NovaActionRecord,
): HotkeyProfile {
  const exists = profile.novaActions.some((a) => a.id === draft.id);
  return {
    ...profile,
    novaActions: exists
      ? profile.novaActions.map((a) => (a.id === draft.id ? draft : a))
      : [...profile.novaActions, draft],
    removedNovaActionIds: (profile.removedNovaActionIds ?? []).filter(
      (id) => id !== draft.id,
    ),
    updatedAt: new Date().toISOString(),
  };
}

const DESK_ASK_BID_IDS = new Set(['nova-buy-ask', 'nova-sell-bid', 'nova-sell-ask']);

function isBareFunctionKey(chord: HotkeyKeyChord, key: string): boolean {
  return (
    chord.key.toLowerCase() === key
    && !chord.ctrl
    && !chord.shift
    && !chord.alt
    && !chord.meta
  );
}

/** Rewrite desk Ask+/Bid- rows to current F1/F2/F5 1-share EH defaults. */
export function applyDeskAskBidHotkeys(
  existing: NovaActionRecord[],
): NovaActionRecord[] {
  const desk = new Map(
    createDefaultNovaActions()
      .filter((row) => DESK_ASK_BID_IDS.has(row.id))
      .map((row) => [row.id, row]),
  );
  return existing.map((row) => {
    const def = desk.get(row.id);
    if (def) {
      return {
        ...row,
        name: def.name,
        key: def.key,
        params: { ...def.params },
        enabled: true,
      };
    }
    if (
      isBareFunctionKey(row.key, 'f1')
      || isBareFunctionKey(row.key, 'f2')
      || isBareFunctionKey(row.key, 'f5')
    ) {
      return { ...row, key: { label: '', key: '' } };
    }
    return row;
  });
}

export function migrateProfile(raw: unknown): HotkeyProfile | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Partial<HotkeyProfile> & { novaActions?: unknown };
  if (!Array.isArray(obj.records)) return null;
  const records = obj.records.filter(isRecord);
  const removedNovaActionIds = parseRemovedIds(obj.removedNovaActionIds);
  const novaActions = Array.isArray(obj.novaActions)
    ? mergeMissingDefaultNovaActions(
      obj.novaActions.filter(isNovaAction),
      removedNovaActionIds,
    )
    : createDefaultNovaActions();
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName: typeof obj.fileName === 'string' ? obj.fileName : 'hotkey.htk',
    records,
    novaActions: novaActions.length > 0 ? novaActions : createDefaultNovaActions(),
    shortcutsMenuKey: isKeyChord(obj.shortcutsMenuKey)
      ? obj.shortcutsMenuKey
      : undefined,
    removedNovaActionIds:
      removedNovaActionIds.length > 0 ? removedNovaActionIds : undefined,
    updatedAt:
      typeof obj.updatedAt === 'string' ? obj.updatedAt : new Date().toISOString(),
  };
}

/** True when this tab has not applied the current F1/F2/F5 desk epoch yet. */
export function deskAskBidEpochNeedsApply(): boolean {
  try {
    return localStorage.getItem(DESK_ASK_BID_HOTKEY_EPOCH_KEY) !== DESK_ASK_BID_HOTKEY_EPOCH;
  } catch {
    return false;
  }
}

/** One-time F1/F2 Ask+/Bid- rewrite so older local profiles pick up the desk pair. */
function applyDeskAskBidEpoch(profile: HotkeyProfile): HotkeyProfile {
  try {
    if (localStorage.getItem(DESK_ASK_BID_HOTKEY_EPOCH_KEY) === DESK_ASK_BID_HOTKEY_EPOCH) {
      return profile;
    }
    localStorage.setItem(DESK_ASK_BID_HOTKEY_EPOCH_KEY, DESK_ASK_BID_HOTKEY_EPOCH);
    const next: HotkeyProfile = {
      ...profile,
      novaActions: applyDeskAskBidHotkeys(profile.novaActions ?? []),
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(HOTKEY_STORAGE_KEY, JSON.stringify(next));
    return next;
  } catch {
    return {
      ...profile,
      novaActions: applyDeskAskBidHotkeys(profile.novaActions ?? []),
    };
  }
}

/** One-time drop of stored menu chord when the product default changes. */
function applyMenuDefaultEpoch(profile: HotkeyProfile): HotkeyProfile {
  try {
    if (
      localStorage.getItem(SHORTCUTS_MENU_EPOCH_STORAGE_KEY)
      === SHORTCUTS_MENU_DEFAULT_EPOCH
    ) {
      return profile;
    }
    localStorage.setItem(
      SHORTCUTS_MENU_EPOCH_STORAGE_KEY,
      SHORTCUTS_MENU_DEFAULT_EPOCH,
    );
    if (!profile.shortcutsMenuKey) return profile;
    const next: HotkeyProfile = {
      ...profile,
      shortcutsMenuKey: undefined,
      updatedAt: new Date().toISOString(),
    };
    // Persist without re-entering loadProfile.
    localStorage.setItem(HOTKEY_STORAGE_KEY, JSON.stringify(next));
    return next;
  } catch {
    return profile;
  }
}

export function loadProfile(): HotkeyProfile {
  try {
    const raw = localStorage.getItem(HOTKEY_STORAGE_KEY);
    if (!raw) {
      try {
        localStorage.setItem(
          SHORTCUTS_MENU_EPOCH_STORAGE_KEY,
          SHORTCUTS_MENU_DEFAULT_EPOCH,
        );
        localStorage.setItem(DESK_ASK_BID_HOTKEY_EPOCH_KEY, DESK_ASK_BID_HOTKEY_EPOCH);
      } catch {
        /* ignore */
      }
      return createEmptyProfile();
    }
    const parsed = JSON.parse(raw) as unknown;
    const profile = migrateProfile(parsed) ?? createEmptyProfile();
    return applyDeskAskBidEpoch(applyMenuDefaultEpoch(profile));
  } catch {
    return createEmptyProfile();
  }
}

export function saveProfile(profile: HotkeyProfile): void {
  const next: HotkeyProfile = {
    ...profile,
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    novaActions: profile.novaActions ?? createDefaultNovaActions(),
    updatedAt: new Date().toISOString(),
  };
  localStorage.setItem(HOTKEY_STORAGE_KEY, JSON.stringify(next));
}

export function clearProfile(): void {
  localStorage.removeItem(HOTKEY_STORAGE_KEY);
}

export function restoreDefaultNovaActions(profile: HotkeyProfile): HotkeyProfile {
  return {
    ...profile,
    novaActions: createDefaultNovaActions(),
    removedNovaActionIds: [],
    updatedAt: new Date().toISOString(),
  };
}
