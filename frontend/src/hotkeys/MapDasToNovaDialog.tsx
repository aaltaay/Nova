/**
 * Confirm mapping a DAS import row → typed Nova Action (disabled until user enables).
 */

import { NOVA_ACTION_KIND_LABELS } from '../constants';
import { formatKeyChord } from './htkFormat';
import type { MapSuggestion } from './mapDasToNovaAction';
import type { HotkeyRecord } from './types';

type Props = {
  record: HotkeyRecord;
  suggestion: Extract<MapSuggestion, { ok: true }>;
  onConfirm: () => void;
  onCancel: () => void;
};

export function MapDasToNovaDialog({
  record,
  suggestion,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <div className="hotkey-editor-backdrop" role="dialog" aria-label="Map to Nova Action">
      <div className="hotkey-editor">
        <h3 className="nova-os-section-title">Map to Nova Action</h3>
        <p className="na-muted">
          Creates a typed Nova Action from this DAS row. It starts <strong>disabled</strong>
          — enable it in the Nova Actions table when ready. The raw DAS command is never run.
        </p>
        <dl className="map-das-preview">
          <div>
            <dt>DAS name</dt>
            <dd>{record.name}</dd>
          </div>
          <div>
            <dt>Key</dt>
            <dd><kbd>{formatKeyChord(record.key)}</kbd></dd>
          </div>
          <div>
            <dt>Nova Action</dt>
            <dd>{NOVA_ACTION_KIND_LABELS[suggestion.kind]}</dd>
          </div>
          <div>
            <dt>Params</dt>
            <dd>
              {suggestion.kind === 'exit_pos_pct' && `${suggestion.params.percent ?? 50}%`}
              {(suggestion.kind === 'buy_limit_ask_offset'
                || suggestion.kind === 'sell_limit_bid_offset') && (
                <>
                  {suggestion.params.shares ?? 100} sh · ±
                  {suggestion.params.offsetDollars ?? 0.05}
                </>
              )}
              {(suggestion.kind === 'cancel_symbol'
                || suggestion.kind === 'cancel_and_exit'
                || suggestion.kind === 'exit_pos') && '—'}
            </dd>
          </div>
        </dl>
        <div className="hotkey-editor-actions">
          <button type="button" className="btn-primary" onClick={onConfirm}>
            Create Nova Action
          </button>
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
