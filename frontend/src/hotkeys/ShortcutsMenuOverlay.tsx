/**
 * Global shortcuts cheat-sheet overlay — peek/pin + double-click / Edit rebind.
 */

import {
  SHORTCUTS_MENU_HINT_PEEK,
  SHORTCUTS_MENU_HINT_PINNED,
  SHORTCUTS_MENU_TITLE,
} from '../constants';
import { ShortcutRebindSession } from './ShortcutRebindSession';
import type { ShortcutCatalogSection, ShortcutRebindTarget } from './shortcutsCatalog';
import type { ShortcutOccupiedSlot } from './shortcutConflicts';
import type { ShortcutsMenuMode } from './shortcutsMenuState';
import type { HotkeyKeyChord } from './types';

type Props = {
  mode: ShortcutsMenuMode;
  sections: ShortcutCatalogSection[];
  occupied: ShortcutOccupiedSlot[];
  rebindTarget: ShortcutRebindTarget | null;
  rebindExcludeId: string | null;
  rebindConflict: string | null;
  onClosePinned: () => void;
  onStartRebind: (target: ShortcutRebindTarget, excludeId: string) => void;
  onApplyRebind: (target: ShortcutRebindTarget, chord: HotkeyKeyChord) => void;
  onRebindConflict: (message: string) => void;
  onCancelRebind: () => void;
};

export function ShortcutsMenuOverlay({
  mode,
  sections,
  occupied,
  rebindTarget,
  rebindExcludeId,
  rebindConflict,
  onClosePinned,
  onStartRebind,
  onApplyRebind,
  onRebindConflict,
  onCancelRebind,
}: Props) {
  if (mode === 'closed') return null;
  const pinned = mode === 'pinned';

  const beginRebind = (target: ShortcutRebindTarget, excludeId: string) => {
    onStartRebind(target, excludeId);
  };

  return (
    <div
      className={`shortcuts-menu-backdrop${pinned ? ' shortcuts-menu-backdrop--pinned' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label={SHORTCUTS_MENU_TITLE}
      onMouseDown={(e) => {
        if (pinned && e.target === e.currentTarget && !rebindTarget) onClosePinned();
      }}
    >
      <div className="shortcuts-menu-panel">
        <header className="shortcuts-menu-header">
          <h2 className="shortcuts-menu-title">{SHORTCUTS_MENU_TITLE}</h2>
          <p className="na-muted shortcuts-menu-hint">
            {pinned ? SHORTCUTS_MENU_HINT_PINNED : SHORTCUTS_MENU_HINT_PEEK}
          </p>
          {rebindTarget && rebindExcludeId && (
            <ShortcutRebindSession
              key={`${rebindTarget.type}-${rebindExcludeId}`}
              target={rebindTarget}
              excludeId={rebindExcludeId}
              occupied={occupied}
              onApplied={onApplyRebind}
              onConflict={onRebindConflict}
              onCancel={onCancelRebind}
            />
          )}
          {rebindConflict && (
            <p className="shortcuts-menu-conflict" role="alert">{rebindConflict}</p>
          )}
        </header>
        <div className="shortcuts-menu-body">
          {sections.map((section) => (
            <section key={section.id} className="shortcuts-menu-section">
              <h3 className="shortcuts-menu-section-title">{section.title}</h3>
              <ul className="shortcuts-menu-list">
                {section.rows.map((row) => (
                  <li
                    key={row.id}
                    className={`shortcuts-menu-row${row.rebind ? ' shortcuts-menu-row--rebindable' : ''}${
                      rebindExcludeId === row.id ? ' shortcuts-menu-row--recording' : ''
                    }`}
                    title={row.rebind ? 'Double-click or press Edit to change shortcut' : undefined}
                    onDoubleClick={(e) => {
                      if (!row.rebind) return;
                      e.preventDefault();
                      e.stopPropagation();
                      beginRebind(row.rebind, row.id);
                    }}
                  >
                    <kbd>{row.chord}</kbd>
                    <span className="shortcuts-menu-label">
                      {row.label}
                      {row.detail && (
                        <span className="na-muted shortcuts-menu-detail">
                          {` · ${row.detail}`}
                        </span>
                      )}
                    </span>
                    {row.rebind && (
                      <button
                        type="button"
                        className="shortcuts-menu-edit-btn"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          beginRebind(row.rebind!, row.id);
                        }}
                      >
                        Edit
                      </button>
                    )}
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
