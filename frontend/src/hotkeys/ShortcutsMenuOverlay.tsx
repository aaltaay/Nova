/**
 * Global shortcuts cheat-sheet overlay (Ctrl+M).
 */

import {
  SHORTCUTS_MENU_HINT_PEEK,
  SHORTCUTS_MENU_HINT_PINNED,
  SHORTCUTS_MENU_TITLE,
} from '../constants';
import type { ShortcutCatalogSection } from './shortcutsCatalog';
import type { ShortcutsMenuMode } from './shortcutsMenuState';

type Props = {
  mode: ShortcutsMenuMode;
  sections: ShortcutCatalogSection[];
  onClosePinned: () => void;
};

export function ShortcutsMenuOverlay({ mode, sections, onClosePinned }: Props) {
  if (mode === 'closed') return null;
  const pinned = mode === 'pinned';

  return (
    <div
      className={`shortcuts-menu-backdrop${pinned ? ' shortcuts-menu-backdrop--pinned' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label={SHORTCUTS_MENU_TITLE}
      onMouseDown={(e) => {
        if (pinned && e.target === e.currentTarget) onClosePinned();
      }}
    >
      <div className="shortcuts-menu-panel">
        <header className="shortcuts-menu-header">
          <h2 className="shortcuts-menu-title">{SHORTCUTS_MENU_TITLE}</h2>
          <p className="na-muted shortcuts-menu-hint">
            {pinned ? SHORTCUTS_MENU_HINT_PINNED : SHORTCUTS_MENU_HINT_PEEK}
          </p>
        </header>
        <div className="shortcuts-menu-body">
          {sections.map((section) => (
            <section key={section.id} className="shortcuts-menu-section">
              <h3 className="shortcuts-menu-section-title">{section.title}</h3>
              <ul className="shortcuts-menu-list">
                {section.rows.map((row) => (
                  <li key={row.id} className="shortcuts-menu-row">
                    <kbd>{row.chord}</kbd>
                    <span className="shortcuts-menu-label">
                      {row.label}
                      {row.detail && (
                        <span className="na-muted shortcuts-menu-detail">
                          {` · ${row.detail}`}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
