import { useCallback, useState } from 'react';
import type { NovaTheme } from '../constants';
import { initThemeFromStorage, setTheme, toggleTheme } from './themePrefs';

export function useTheme() {
  const [theme, setThemeState] = useState<NovaTheme>(() => initThemeFromStorage());

  const set = useCallback((next: NovaTheme) => {
    setTheme(next);
    setThemeState(next);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => toggleTheme(prev));
  }, []);

  return { theme, setTheme: set, toggleTheme: toggle };
}
