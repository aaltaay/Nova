/**
 * Hotkeys Settings manager — master-detail (Webull-style second window).
 */

import { useEffect, useMemo, useState } from 'react';
import {
  HOTKEYS_SETTINGS_DIALOG_TITLE,
  HOTKEYS_SETTINGS_DONE,
  HOTKEYS_SETTINGS_LIST_TITLE,
  HOTKEYS_SETTINGS_RESET,
} from '../constants';
import { CreateCustomButtonDialog } from './CreateCustomButtonDialog';
import { formatKeyChord } from './htkFormat';
import { HotkeysSettingsDetail } from './HotkeysSettingsDetail';
import { novaActionConflictMessage } from './novaActionConflict';
import { formatNovaActionListLabel } from './novaActionFormat';
import type { NovaActionRecord } from './novaActionTypes';

export function HotkeysSettingsDialog({
  actions,
  initialSelectedId,
  onChange,
  onRestoreDefaults,
  onDelete,
  onClose,
}: {
  actions: NovaActionRecord[];
  initialSelectedId?: string | null;
  onChange: (next: NovaActionRecord[]) => void;
  onRestoreDefaults: () => void;
  onDelete?: (id: string) => void;
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(
    initialSelectedId ?? actions[0]?.id ?? null,
  );
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !creating) {
        e.stopPropagation();
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [onClose, creating]);

  useEffect(() => {
    if (selectedId && !actions.some((a) => a.id === selectedId)) {
      setSelectedId(actions[0]?.id ?? null);
    }
  }, [actions, selectedId]);

  const selected = actions.find((a) => a.id === selectedId) ?? null;
  const conflictMsg = useMemo(
    () => (selected ? novaActionConflictMessage(selected, actions) : null),
    [selected, actions],
  );

  function patchSelected(next: NovaActionRecord) {
    onChange(actions.map((a) => (a.id === next.id ? next : a)));
  }

  return (
    <div
      className="hotkey-editor-backdrop hk-settings-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={HOTKEYS_SETTINGS_DIALOG_TITLE}
      data-testid="hotkeys-settings-dialog"
    >
      <div className="hk-settings-dialog">
        <header className="hk-dialog-header">
          <h3>{HOTKEYS_SETTINGS_DIALOG_TITLE}</h3>
          <button type="button" className="hk-dialog-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="hk-settings-body">
          <aside className="hk-settings-list-pane">
            <div className="hk-settings-list-head">
              <span>{HOTKEYS_SETTINGS_LIST_TITLE}</span>
              <button
                type="button"
                className="hk-settings-add"
                aria-label="Create customized button"
                data-testid="hotkeys-settings-add"
                onClick={() => setCreating(true)}
              >
                +
              </button>
            </div>
            <div className="hk-settings-group">
              <div className="hk-settings-group-label">Stocks</div>
              <ul className="hk-settings-list">
                {actions.map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      className={`hk-settings-list-item${
                        row.id === selectedId ? ' is-selected' : ''
                      }`}
                      onClick={() => setSelectedId(row.id)}
                    >
                      <span>{formatNovaActionListLabel(row)}</span>
                      <kbd>{row.key.key ? formatKeyChord(row.key) : '-'}</kbd>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <section className="hk-settings-detail-pane">
            {selected ? (
              <HotkeysSettingsDetail
                action={selected}
                conflictMsg={conflictMsg}
                onChange={patchSelected}
                onDelete={onDelete}
              />
            ) : (
              <p className="na-muted">Select a hotkey or create a new one.</p>
            )}
          </section>
        </div>

        <footer className="hk-dialog-footer">
          <button type="button" className="btn-secondary" onClick={onRestoreDefaults}>
            {HOTKEYS_SETTINGS_RESET}
          </button>
          <button
            type="button"
            className="btn-primary"
            data-testid="hotkeys-settings-done"
            onClick={onClose}
          >
            {HOTKEYS_SETTINGS_DONE}
          </button>
        </footer>
      </div>

      {creating && (
        <CreateCustomButtonDialog
          onCancel={() => setCreating(false)}
          onCreate={(action) => {
            onChange([...actions, action]);
            setSelectedId(action.id);
            setCreating(false);
          }}
        />
      )}
    </div>
  );
}
