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
  HOTKEY_ACTIONS,
  NOVA_ACTION_KINDS,
  type HotkeyAction,
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
  extras?: Pick<HotkeyProfile, 'automationBindings' | 'shortcutsMenuKey'>,
): HotkeyProfile {
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName,
    records,
    novaActions: novaActions ?? createDefaultNovaActions(),
    automationBindings: extras?.automationBindings,
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

function migrateAutomationBindings(
  raw: unknown,
): Partial<Record<HotkeyAction, HotkeyKeyChord>> | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const out: Partial<Record<HotkeyAction, HotkeyKeyChord>> = {};
  for (const action of HOTKEY_ACTIONS) {
    const chord = (raw as Record<string, unknown>)[action];
    if (isKeyChord(chord)) out[action] = chord;
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

/** Ensure newly shipped default Nova Actions appear on older local profiles. */
export function mergeMissingDefaultNovaActions(
  existing: NovaActionRecord[],
): NovaActionRecord[] {
  const defaults = createDefaultNovaActions();
  const byId = new Map(existing.map((a) => [a.id, a]));
  const kinds = new Set(existing.map((a) => a.kind));
  const merged = [...existing];
  for (const def of defaults) {
    if (!byId.has(def.id) && !kinds.has(def.kind)) {
      merged.push(def);
      kinds.add(def.kind);
    }
  }
  return merged;
}

export function migrateProfile(raw: unknown): HotkeyProfile | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Partial<HotkeyProfile> & { novaActions?: unknown };
  if (!Array.isArray(obj.records)) return null;
  const records = obj.records.filter(isRecord);
  const novaActions = Array.isArray(obj.novaActions)
    ? mergeMissingDefaultNovaActions(obj.novaActions.filter(isNovaAction))
    : createDefaultNovaActions();
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName: typeof obj.fileName === 'string' ? obj.fileName : 'hotkey.htk',
    records,
    novaActions: novaActions.length > 0 ? novaActions : createDefaultNovaActions(),
    automationBindings: migrateAutomationBindings(obj.automationBindings),
    shortcutsMenuKey: isKeyChord(obj.shortcutsMenuKey)
      ? obj.shortcutsMenuKey
      : undefined,
    updatedAt:
      typeof obj.updatedAt === 'string' ? obj.updatedAt : new Date().toISOString(),
  };
}

export function loadProfile(): HotkeyProfile {
  try {
    const raw = localStorage.getItem(HOTKEY_STORAGE_KEY);
    if (!raw) return createEmptyProfile();
    const parsed = JSON.parse(raw) as unknown;
    return migrateProfile(parsed) ?? createEmptyProfile();
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
    updatedAt: new Date().toISOString(),
  };
}
