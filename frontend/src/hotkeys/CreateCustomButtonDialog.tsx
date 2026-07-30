/**
 * Create a Customized Button — third window in Hotkeys Settings flow.
 */

import { useMemo, useState } from 'react';
import {
  HOTKEYS_CREATE_APPLY_LABEL,
  HOTKEYS_CREATE_APPLY_STOCK,
  HOTKEYS_CREATE_CANCEL,
  HOTKEYS_CREATE_DIALOG_TITLE,
  HOTKEYS_CREATE_NAME_LABEL,
  HOTKEYS_CREATE_SIDE_BUY,
  HOTKEYS_CREATE_SIDE_LABEL,
  HOTKEYS_CREATE_SIDE_SELL,
  HOTKEYS_CREATE_SUBMIT,
  HOTKEYS_DEFAULT_CUSTOM_NAME,
  NOVA_ACTION_KIND_LABELS,
  type NovaActionKind,
} from '../constants';
import {
  createBlankNovaAction,
  defaultKindForSide,
  kindsForSide,
  type CustomButtonSide,
} from './createBlankNovaAction';
import type { NovaActionRecord } from './novaActionTypes';

export function CreateCustomButtonDialog({
  onCancel,
  onCreate,
}: {
  onCancel: () => void;
  onCreate: (action: NovaActionRecord) => void;
}) {
  const [name, setName] = useState(HOTKEYS_DEFAULT_CUSTOM_NAME);
  const [side, setSide] = useState<CustomButtonSide>('buy');
  const kinds = useMemo(() => kindsForSide(side), [side]);
  const [kind, setKind] = useState<NovaActionKind>(() => defaultKindForSide('buy'));

  function onSideChange(next: CustomButtonSide) {
    setSide(next);
    setKind(defaultKindForSide(next));
  }

  return (
    <div
      className="hotkey-editor-backdrop hk-create-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={HOTKEYS_CREATE_DIALOG_TITLE}
      data-testid="hotkeys-create-dialog"
    >
      <div className="hk-create-dialog">
        <header className="hk-dialog-header">
          <h3>{HOTKEYS_CREATE_DIALOG_TITLE}</h3>
          <button type="button" className="hk-dialog-close" onClick={onCancel} aria-label="Close">
            ×
          </button>
        </header>

        <label className="hk-field">
          <span>{HOTKEYS_CREATE_NAME_LABEL}</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            data-testid="hotkeys-create-name"
          />
        </label>

        <label className="hk-field">
          <span>{HOTKEYS_CREATE_APPLY_LABEL}</span>
          <select disabled value="stock">
            <option value="stock">{HOTKEYS_CREATE_APPLY_STOCK}</option>
          </select>
        </label>

        <div className="hk-field">
          <span>{HOTKEYS_CREATE_SIDE_LABEL}</span>
          <div className="hk-side-toggle" role="group" aria-label={HOTKEYS_CREATE_SIDE_LABEL}>
            <button
              type="button"
              className={`hk-side-buy${side === 'buy' ? ' is-active' : ''}`}
              onClick={() => onSideChange('buy')}
            >
              {HOTKEYS_CREATE_SIDE_BUY}
            </button>
            <button
              type="button"
              className={`hk-side-sell${side === 'sell' ? ' is-active' : ''}`}
              onClick={() => onSideChange('sell')}
            >
              {HOTKEYS_CREATE_SIDE_SELL}
            </button>
          </div>
        </div>

        <label className="hk-field">
          <span>Action</span>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as NovaActionKind)}
            data-testid="hotkeys-create-kind"
          >
            {kinds.map((k) => (
              <option key={k} value={k}>{NOVA_ACTION_KIND_LABELS[k]}</option>
            ))}
          </select>
        </label>

        <footer className="hk-dialog-footer">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            {HOTKEYS_CREATE_CANCEL}
          </button>
          <button
            type="button"
            className="btn-primary"
            data-testid="hotkeys-create-submit"
            onClick={() => onCreate(createBlankNovaAction(name, kind))}
          >
            {HOTKEYS_CREATE_SUBMIT}
          </button>
        </footer>
      </div>
    </div>
  );
}
