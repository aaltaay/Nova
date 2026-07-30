/**
 * Right pane of Hotkeys Settings — edit selected Nova Action.
 */

import { useState } from 'react';
import {
  NOVA_ACTION_KIND_LABELS,
  NOVA_ACTION_KINDS,
  type NovaActionKind,
} from '../constants';
import { formatKeyChord, parseKeyChord } from './htkFormat';
import { KeyCapture } from './KeyCapture';
import { describeNovaAction } from './novaActionFormat';
import type { NovaActionRecord } from './novaActionTypes';

export function HotkeysSettingsDetail({
  action,
  conflictMsg,
  onChange,
}: {
  action: NovaActionRecord;
  conflictMsg: string | null;
  onChange: (next: NovaActionRecord) => void;
}) {
  const [capturing, setCapturing] = useState(false);

  return (
    <div className="hk-settings-detail" data-testid="hotkeys-settings-detail">
      <h3 className="hk-settings-detail-title">{action.name}</h3>
      <p className="na-muted hk-settings-detail-desc">{describeNovaAction(action)}</p>

      <label className="hk-field">
        <span>Name</span>
        <input
          value={action.name}
          onChange={(e) => onChange({ ...action, name: e.target.value })}
        />
      </label>

      <label className="hk-field">
        <span>Hot Key</span>
        <div className="hotkey-editor-key-row">
          <input
            value={formatKeyChord(action.key)}
            onChange={(e) => onChange({ ...action, key: parseKeyChord(e.target.value) })}
            data-testid="hotkeys-detail-key"
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

      <label className="hk-field">
        <span>Order Type / Action</span>
        <select
          value={action.kind}
          onChange={(e) => {
            const kind = e.target.value as NovaActionKind;
            onChange({ ...action, kind });
          }}
        >
          {NOVA_ACTION_KINDS.map((k) => (
            <option key={k} value={k}>{NOVA_ACTION_KIND_LABELS[k]}</option>
          ))}
        </select>
      </label>

      {(action.kind === 'buy_limit_ask_offset' || action.kind === 'sell_limit_bid_offset') && (
        <div className="hk-qty-row">
          <label className="hk-field hk-field-grow">
            <span>Quantity</span>
            <input
              type="number"
              value={action.params.shares ?? 100}
              onChange={(e) => onChange({
                ...action,
                params: { ...action.params, shares: Number(e.target.value) },
              })}
            />
          </label>
          <span className="hk-qty-unit is-active" title="Shares">≡</span>
          <label className="hk-field hk-field-grow">
            <span>Offset ($)</span>
            <input
              type="number"
              step="0.01"
              value={action.params.offsetDollars ?? 0.05}
              onChange={(e) => onChange({
                ...action,
                params: { ...action.params, offsetDollars: Number(e.target.value) },
              })}
            />
          </label>
        </div>
      )}

      {action.kind === 'exit_pos_pct' && (
        <label className="hk-field">
          <span>Quantity (%)</span>
          <input
            type="number"
            value={action.params.percent ?? 50}
            onChange={(e) => onChange({
              ...action,
              params: { ...action.params, percent: Number(e.target.value) },
            })}
          />
        </label>
      )}

      <label className="hk-check-row">
        <input
          type="checkbox"
          checked={action.enabled}
          onChange={() => onChange({ ...action, enabled: !action.enabled })}
        />
        <span>Enabled</span>
      </label>
      <label className="hk-check-row">
        <input
          type="checkbox"
          checked={action.showButton}
          onChange={() => onChange({ ...action, showButton: !action.showButton })}
        />
        <span>Show on Trading bar</span>
      </label>

      {conflictMsg && <p className="empty-state" role="alert">{conflictMsg}</p>}

      {capturing && (
        <KeyCapture
          onCapture={(chord) => {
            onChange({ ...action, key: chord });
            setCapturing(false);
          }}
          onCancel={() => setCapturing(false)}
        />
      )}
    </div>
  );
}
