/**
 * Light/dark appearance prefs — applies data-theme on <html> only.
 */

import {
  THEME_DEFAULT,
  THEME_STORAGE_KEY,
  type NovaTheme,
} from '../constants';

export function isNovaTheme(value: unknown): value is NovaTheme {
  return value === 'light' || value === 'dark';
}

export function readStoredTheme(
  storage: Pick<Storage, 'getItem'> = localStorage,
): NovaTheme {
  try {
    const raw = storage.getItem(THEME_STORAGE_KEY);
    return isNovaTheme(raw) ? raw : THEME_DEFAULT;
  } catch {
    return THEME_DEFAULT;
  }
}

export function applyTheme(theme: NovaTheme): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.setAttribute('data-theme', theme);
  root.style.colorScheme = theme;
}

export function persistTheme(
  theme: NovaTheme,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* quota / private mode — theme still applied in DOM */
  }
}

/** Read storage, apply to <html>, return active theme. */
export function initThemeFromStorage(
  storage: Pick<Storage, 'getItem'> = localStorage,
): NovaTheme {
  const theme = readStoredTheme(storage);
  applyTheme(theme);
  return theme;
}

export function setTheme(
  theme: NovaTheme,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  applyTheme(theme);
  persistTheme(theme, storage);
}

export function toggleTheme(
  current: NovaTheme,
  storage: Pick<Storage, 'setItem'> = localStorage,
): NovaTheme {
  const next: NovaTheme = current === 'dark' ? 'light' : 'dark';
  setTheme(next, storage);
  return next;
}
