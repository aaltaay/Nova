/**
 * Pure helpers for module visibility persisted in localStorage (Phase 4).
 */
import { MODULE_VISIBILITY_STORAGE_KEY } from '../constants';
import { listModules } from './registry';

export type ModuleVisibilityMap = Record<string, boolean>;

export function defaultModuleVisibility(): ModuleVisibilityMap {
  const out: ModuleVisibilityMap = {};
  for (const m of listModules()) {
    out[m.id] = m.defaultVisible !== false;
  }
  return out;
}

export function parseModuleVisibility(raw: string | null): ModuleVisibilityMap {
  const base = defaultModuleVisibility();
  if (!raw) return base;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return base;
    const next = { ...base };
    for (const [id, val] of Object.entries(parsed as Record<string, unknown>)) {
      if (id in base && typeof val === 'boolean') next[id] = val;
    }
    return next;
  } catch {
    return base;
  }
}

export function loadModuleVisibility(
  storage: Pick<Storage, 'getItem'> = localStorage,
): ModuleVisibilityMap {
  try {
    return parseModuleVisibility(storage.getItem(MODULE_VISIBILITY_STORAGE_KEY));
  } catch {
    return defaultModuleVisibility();
  }
}

export function saveModuleVisibility(
  map: ModuleVisibilityMap,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(MODULE_VISIBILITY_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* quota / private mode — ignore */
  }
}

export function isModuleVisible(id: string, map: ModuleVisibilityMap): boolean {
  if (id in map) return map[id] !== false;
  return true;
}
