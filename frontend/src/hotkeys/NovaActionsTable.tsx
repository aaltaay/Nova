/**
 * Editable Nova Actions table in Settings → Hotkeys (Phase G3).
 */

import { useMemo, useState } from 'react';
import {
  HOTKEY_DEFAULTS,
  NOVA_ACTION_KIND_LABELS,
  NOVA_ACTION_NEEDS_DEPTH,
  type HotkeyAction,
} from '../constants';
import { formatHotkeyLabel, chordsConflict, chordToBinding } from '../hooks/hotkeyUtils';
import { formatKeyChord } from './htkFormat';
import { NovaActionEditor } from './NovaActionEditor';
import type { NovaActionRecord } from './novaActionTypes';
import type { HotkeyKeyChord } from './types';
import { useTopOfBook } from './TopOfBookContext';

interface Props {
  actions: NovaActionRecord[];
  onChange: (next: NovaActionRecord[]) => void;
  onRestoreDefaults: () => void;
}

function automationChords(): HotkeyKeyChord[] {
  return (Object.keys(HOTKEY_DEFAULTS) as HotkeyAction[]).map((a) => {
    const b = HOTKEY_DEFAULTS[a];
    return {
      label: formatHotkeyLabel(b),
      key: b.key,
      ctrl: b.ctrl,
      shift: b.shift,
      alt: b.alt,
      meta: b.meta,
    };
  });
}

function paramsCell(row: NovaActionRecord, liveDisabled: boolean): string {
  if (row.kind === 'exit_pos_pct') return `${row.params.percent ?? 50}%`;
  if (row.kind === 'buy_limit_ask_offset' || row.kind === 'sell_limit_bid_offset') {
    const base = `${row.params.shares ?? 100} sh · ±${row.params.offsetDollars ?? 0.05}`;
    return liveDisabled ? `${base} · L2` : base;
  }
  if (row.kind === 'exit_pos' || row.kind === 'cancel_and_exit') return 'Pos';
  if (row.kind === 'cancel_symbol') return 'All';
  return '—';
}

export function NovaActionsTable({ actions, onChange, onRestoreDefaults }: Props) {
  const { topOfBook } = useTopOfBook();
  const [draft, setDraft] = useState<NovaActionRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const depthOk = Boolean(
    topOfBook?.depthSubscribed && topOfBook.bid != null && topOfBook.ask != null,
  );

  const conflictMsg = useMemo(() => {
    if (!draft) return null;
    for (const other of actions) {
      if (other.id === draft.id) continue;
      if (chordsConflict(draft.key, other.key)) {
        return `Conflicts with Nova Action “${other.name}”`;
      }
    }
    for (const ac of automationChords()) {
      if (chordsConflict(draft.key, ac)) {
        return `Conflicts with Automation shortcut ${formatKeyChord(ac)}`;
      }
    }
    return null;
  }, [draft, actions]);

  function saveEdit() {
    if (!draft) return;
    if (conflictMsg) {
      setError(conflictMsg);
      return;
    }
    if (!chordToBinding(draft.key)) {
      setError('Key chord is required');
      return;
    }
    onChange(actions.map((a) => (a.id === draft.id ? draft : a)));
    setDraft(null);
    setError(null);
  }

  return (
    <div className="nova-actions-table">
      <div className="nova-actions-table-header">
        <h4 className="nova-os-section-title">Nova Actions (executable)</h4>
        <button type="button" className="btn-secondary" onClick={onRestoreDefaults}>
          Restore Nova defaults
        </button>
      </div>
      <p className="na-muted">
        Typed intents only — PIN unlock, spend lock, and place-confirm still apply.
        Ask±/Bid± require live L2 depth for the open symbol.
      </p>

      <table className="hotkey-records-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Action</th>
            <th>Key</th>
            <th>Params</th>
            <th>On</th>
            <th>Button</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {actions.map((row) => {
            const needsDepth = NOVA_ACTION_NEEDS_DEPTH.includes(row.kind);
            const liveDisabled = needsDepth && !depthOk;
            return (
              <tr
                key={row.id}
                className={liveDisabled ? 'nova-action-depth-disabled' : undefined}
              >
                <td>{row.name}</td>
                <td>{NOVA_ACTION_KIND_LABELS[row.kind]}</td>
                <td><kbd>{formatKeyChord(row.key)}</kbd></td>
                <td className="na-muted">{paramsCell(row, liveDisabled)}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.enabled}
                    onChange={() => onChange(
                      actions.map((a) => (a.id === row.id ? { ...a, enabled: !a.enabled } : a)),
                    )}
                    aria-label={`Enable ${row.name}`}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.showButton}
                    onChange={() => onChange(
                      actions.map((a) => (
                        a.id === row.id ? { ...a, showButton: !a.showButton } : a
                      )),
                    )}
                    aria-label={`Show button ${row.name}`}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setDraft({ ...row, params: { ...row.params } });
                      setError(null);
                    }}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {draft && (
        <NovaActionEditor
          draft={draft}
          conflictMsg={conflictMsg}
          error={error}
          onChange={setDraft}
          onSave={saveEdit}
          onCancel={() => { setDraft(null); setError(null); }}
        />
      )}
    </div>
  );
}
