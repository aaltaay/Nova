/** Appearance / color-scheme preferences (theme-only; no layout). */

export type NovaTheme = 'light' | 'dark';

/** localStorage key for light | dark. */
export const THEME_STORAGE_KEY = 'nova.theme';

/** Default appearance — keep dark for trading density; users can switch. */
export const THEME_DEFAULT: NovaTheme = 'dark';
