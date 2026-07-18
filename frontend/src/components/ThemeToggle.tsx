/**
 * Header control: flip light ↔ dark (Apple-ish appearance tokens only).
 */
import { useTheme } from '../theme/useTheme';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const next = theme === 'dark' ? 'Light' : 'Dark';
  return (
    <button
      type="button"
      className="theme-toggle-btn"
      onClick={toggleTheme}
      title={`Switch to ${next.toLowerCase()} appearance`}
      aria-label={`Switch to ${next.toLowerCase()} appearance`}
    >
      {next}
    </button>
  );
}
