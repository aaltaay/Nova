/**
 * Modal editor for a single Nova Action row.
 */

import { useEffect, useState } from 'react';
import {
  NOVA_ACTION_KIND_LABELS,
  NOVA_ACTION_KINDS,
  type NovaActionKind,
} from '../constants';
import { formatKeyChord, parseKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';
import type { HotkeyKeyChord } from './types';

interface Props {
  draft: NovaActionRecord;
  conflictMsg: string | null;
  error: string | null;
  onChange: (next: NovaActionRecord) => void;
  onSave: () => void;
  onCancel: () => void;
}

function CaptureKey({
  onCapture,
  onCancel,
}: {
  onCapture: (c: HotkeyKeyChord) => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === 'Escape') {
        onCancel();
        return;
      }
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;
      const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
      const parts: string[] = [];
      if (e.ctrlKey) parts.push('Ctrl');
      if (e.shiftKey) parts.push('Shift');
      if (e.altKey) parts.push('Alt');
      if (e.metaKey) parts.push('Win');
      parts.push(key === ' ' ? 'Space' : key);
      onCapture(parseKeyChord(parts.join('+')));
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [onCapture, onCancel]);
  return null;
}

export function NovaActionEditor({
  draft,
  conflictMsg,
  error,
  onChange,
  onSave,
  onCancel,
}: Props) {
  const [capturing, setCapturing] = useState(false);

  return (
    <div className="hotkey-editor-backdrop" role="dialog" aria-label="Edit Nova Action">
      <div className="hotkey-editor">
        <h3 className="nova-os-section-title">Edit Nova Action</h3>
        <label className="hotkey-editor-field">
          <span>Name</span>
          <input
            value={draft.name}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
          />
        </label>
        <label className="hotkey-editor-field">
          <span>Action</span>
          <select
            value={draft.kind}
            onChange={(e) => onChange({ ...draft, kind: e.target.value as NovaActionKind })}
          >
            {NOVA_ACTION_KINDS.map((k) => (
              <option key={k} value={k}>{NOVA_ACTION_KIND_LABELS[k]}</option>
            ))}
          </select>
        </label>
        <label className="hotkey-editor-field">
          <span>Key</span>
          <div className="hotkey-editor-key-row">
            <input
              value={formatKeyChord(draft.key)}
              onChange={(e) => onChange({ ...draft, key: parseKeyChord(e.target.value) })}
            />
            <button
              type="button"
              className={capturing ? 'btn-secondary active' : 'btn-secondary'}
              onClick={() => setCapturing((c) => !c)}
            >
              {capturing ? 'Press key…' : 'Capture'}
            </button>
          </div>
        </label>
        {(draft.kind === 'buy_limit_ask_offset' || draft.kind === 'sell_limit_bid_offset') && (
          <>
            <label className="hotkey-editor-field">
              <span>Shares</span>
              <input
                type="number"
                value={draft.params.shares ?? 100}
                onChange={(e) => onChange({
                  ...draft,
                  params: { ...draft.params, shares: Number(e.target.value) },
                })}
              />
            </label>
            <label className="hotkey-editor-field">
              <span>Offset ($)</span>
              <input
                type="number"
                step="0.01"
                value={draft.params.offsetDollars ?? 0.05}
                onChange={(e) => onChange({
                  ...draft,
                  params: { ...draft.params, offsetDollars: Number(e.target.value) },
                })}
              />
            </label>
          </>
        )}
        {draft.kind === 'exit_pos_pct' && (
          <label className="hotkey-editor-field">
            <span>Percent</span>
            <input
              type="number"
              value={draft.params.percent ?? 50}
              onChange={(e) => onChange({
                ...draft,
                params: { ...draft.params, percent: Number(e.target.value) },
              })}
            />
          </label>
        )}
        {(error || conflictMsg) && (
          <p className="empty-state">{error || conflictMsg}</p>
        )}
        <div className="hotkey-editor-actions">
          <button type="button" className="btn-primary" onClick={onSave}>Save</button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setCapturing(false);
              onCancel();
            }}
          >
            Cancel
          </button>
        </div>
      </div>
      {capturing && (
        <CaptureKey
          onCapture={(chord) => {
            onChange({ ...draft, key: chord });
            setCapturing(false);
          }}
          onCancel={() => setCapturing(false)}
        />
      )}
    </div>
  );
}
