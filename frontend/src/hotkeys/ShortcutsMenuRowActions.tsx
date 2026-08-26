/**
 * Per-row Key / Edit / guarded delete on the shortcuts cheat-sheet.
 */

import type { MouseEvent } from 'react';
import {
  SHORTCUTS_MENU_ACTION_BTN,
  SHORTCUTS_MENU_KEY_BTN,
} from '../constants';
import { ConfirmDeleteIconButton } from './ConfirmDeleteIconButton';
import type { ShortcutCatalogRow } from './shortcutsCatalog';

export function ShortcutsMenuRowActions({
  row,
  onRebind,
  onEditAction,
  onDeleteAction,
  onArmDelete,
}: {
  row: ShortcutCatalogRow;
  onRebind: () => void;
  onEditAction?: (id: string) => void;
  onDeleteAction?: (id: string) => void;
  onArmDelete?: () => void;
}) {
  if (!row.rebind) return null;

  const stop = (fn: () => void) => (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    fn();
  };

  return (
    <div className="shortcuts-menu-row-actions">
      <button
        type="button"
        className="shortcuts-menu-key-btn"
        data-testid="shortcuts-menu-key-btn"
        title="Change the keyboard shortcut"
        onClick={stop(onRebind)}
      >
        {SHORTCUTS_MENU_KEY_BTN}
      </button>
      {row.canEditAction && onEditAction && (
        <button
          type="button"
          className="shortcuts-menu-edit-btn"
          data-testid="shortcuts-menu-edit-btn"
          title="Edit this Nova Action"
          onClick={stop(() => onEditAction(row.id))}
        >
          {SHORTCUTS_MENU_ACTION_BTN}
        </button>
      )}
      {row.canDelete && onDeleteAction && (
        <span className="shortcuts-menu-delete-slot">
          <ConfirmDeleteIconButton
            label={row.label}
            onArm={onArmDelete}
            onConfirm={() => onDeleteAction(row.id)}
          />
        </span>
      )}
    </div>
  );
}
