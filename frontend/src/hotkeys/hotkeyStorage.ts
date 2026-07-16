/**
 * Local-first hotkey profile persistence. Never sent to the backend.
 */

import {
  HOTKEY_PROFILE_SCHEMA_VERSION,
  type HotkeyProfile,
  type HotkeyRecord,
} from './types';

export const HOTKEY_STORAGE_KEY = 'nova.hotkeys.profile.v1';

export function createEmptyProfile(fileName = 'hotkey.htk'): HotkeyProfile {
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName,
    records: [],
    updatedAt: new Date().toISOString(),
  };
}

export function profileFromRecords(
  records: HotkeyRecord[],
  fileName: string,
): HotkeyProfile {
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName,
    records,
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

export function migrateProfile(raw: unknown): HotkeyProfile | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Partial<HotkeyProfile>;
  if (!Array.isArray(obj.records)) return null;
  const records = obj.records.filter(isRecord);
  return {
    schemaVersion: HOTKEY_PROFILE_SCHEMA_VERSION,
    fileName: typeof obj.fileName === 'string' ? obj.fileName : 'hotkey.htk',
    records,
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
    updatedAt: new Date().toISOString(),
  };
  localStorage.setItem(HOTKEY_STORAGE_KEY, JSON.stringify(next));
}

export function clearProfile(): void {
  localStorage.removeItem(HOTKEY_STORAGE_KEY);
}
