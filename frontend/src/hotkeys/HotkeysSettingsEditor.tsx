/**
 * Settings > Hot Keys editor: Nova Actions listed on the left, the selected
 * one's fields on the right, Reset / Done in a footer row. It renders inside
 * the Settings section -- there is no second window, so the Settings Close
 * stays the one close and Escape belongs to the sheet.
 */

import { useEffect, useMemo, useState } from 'react';
import {
  HOTKEYS_CREATE_ADD_LABEL,
  HOTKEYS_EDITOR_EMPTY,
  HOTKEYS_EDITOR_GROUP_STOCKS,
  HOTKEYS_EMPTY_LIST,
  HOTKEYS_ROW_DISABLED_TITLE,
  HOTKEYS_SETTINGS_DONE,
  HOTKEYS_SETTINGS_LIST_TITLE,
  HOTKEYS_SETTINGS_RESET,
} from '../constants';
import { CreateCustomButtonForm } from './CreateCustomButtonForm';
import { formatKeyChord } from './htkFormat';
import { HotkeysSettingsDetail } from './HotkeysSettingsDetail';
import { novaActionConflictMessage } from './novaActionConflict';
import { formatNovaActionListLabel } from './novaActionFormat';
import type { NovaActionRecord } from './novaActionTypes';

export function HotkeysSettingsEditor({
  actions,
  initialSelectedId,
  onChange,
  onRestoreDefaults,
  onDelete,
  onDone,
}: {
  actions: NovaActionRecord[];
  initialSelectedId?: string | null;
  onChange: (next: NovaActionRecord[]) => void;
  onRestoreDefaults: () => void;
  onDelete?: (id: string) => void;
  /** Hands the operator back to the desk (the Settings sheet closes). */
  onDone?: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(
    initialSelectedId ?? actions[0]?.id ?? null,
  );
  const [creating, setCreating] = useState(false);

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
    <section
      className="hk-editor"
      aria-label={HOTKEYS_SETTINGS_LIST_TITLE}
      data-testid="hotkeys-settings-editor"
    >
      <aside className="hk-editor-list-pane">
        <div className="hk-editor-list-head">
          <span>{HOTKEYS_SETTINGS_LIST_TITLE}</span>
          <button
            type="button"
            className="hk-editor-add"
            aria-label={HOTKEYS_CREATE_ADD_LABEL}
            title={HOTKEYS_CREATE_ADD_LABEL}
            data-testid="hotkeys-settings-add"
            onClick={() => setCreating(true)}
          >
            +
          </button>
        </div>
        <div className="hk-editor-list-scroll">
          <div className="hk-editor-group-label">{HOTKEYS_EDITOR_GROUP_STOCKS}</div>
          {actions.length === 0 ? (
            <p className="hk-editor-empty">{HOTKEYS_EMPTY_LIST}</p>
          ) : (
            <ul className="hk-editor-list" data-testid="hotkeys-settings-list">
              {actions.map((row) => {
                const isSelected = row.id === selectedId && !creating;
                return (
                  <li key={row.id}>
                    <button
                      type="button"
                      className={`hk-editor-row${isSelected ? ' is-selected' : ''}${
                        row.enabled ? '' : ' is-off'
                      }`}
                      aria-current={isSelected ? 'true' : undefined}
                      title={row.enabled ? undefined : HOTKEYS_ROW_DISABLED_TITLE}
                      onClick={() => {
                        setCreating(false);
                        setSelectedId(row.id);
                      }}
                    >
                      <span className="hk-editor-row-name">
                        {formatNovaActionListLabel(row)}
                      </span>
                      <kbd className="hk-editor-row-key">
                        {row.key.key ? formatKeyChord(row.key) : '-'}
                      </kbd>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      <div className="hk-editor-detail-pane">
        {creating ? (
          <CreateCustomButtonForm
            onCancel={() => setCreating(false)}
            onCreate={(action) => {
              onChange([...actions, action]);
              setSelectedId(action.id);
              setCreating(false);
            }}
          />
        ) : selected ? (
          <HotkeysSettingsDetail
            action={selected}
            conflictMsg={conflictMsg}
            onChange={patchSelected}
            onDelete={onDelete}
          />
        ) : (
          <p className="hk-editor-empty">{HOTKEYS_EDITOR_EMPTY}</p>
        )}
      </div>

      <footer className="hk-editor-foot">
        <button type="button" className="btn-secondary" onClick={onRestoreDefaults}>
          {HOTKEYS_SETTINGS_RESET}
        </button>
        {onDone && (
          <button
            type="button"
            className="btn-primary"
            data-testid="hotkeys-settings-done"
            onClick={onDone}
          >
            {HOTKEYS_SETTINGS_DONE}
          </button>
        )}
      </footer>
    </section>
  );
}
