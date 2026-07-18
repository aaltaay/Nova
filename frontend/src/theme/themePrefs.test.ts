/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { THEME_STORAGE_KEY } from '../constants';
import {
  applyTheme,
  initThemeFromStorage,
  isNovaTheme,
  readStoredTheme,
  setTheme,
  toggleTheme,
} from './themePrefs';

describe('themePrefs', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.style.colorScheme = '';
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('isNovaTheme accepts only light|dark', () => {
    expect(isNovaTheme('light')).toBe(true);
    expect(isNovaTheme('dark')).toBe(true);
    expect(isNovaTheme('system')).toBe(false);
  });

  it('defaults to dark when unset', () => {
    expect(readStoredTheme()).toBe('dark');
  });

  it('initThemeFromStorage applies data-theme and color-scheme', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light');
    expect(initThemeFromStorage()).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.style.colorScheme).toBe('light');
  });

  it('toggleTheme flips and persists', () => {
    setTheme('dark');
    expect(toggleTheme('dark')).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('applyTheme sets attributes without storage', () => {
    applyTheme('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});
