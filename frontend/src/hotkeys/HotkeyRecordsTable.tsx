import { useMemo } from 'react';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { formatKeyChord } from './htkFormat';
import {
  HOTKEY_COMPAT_LABELS,
  type HotkeyRecord,
  type HotkeyRecordAnalysis,
} from './types';

type Props = {
  rows: HotkeyRecord[];
  selectedId: string | null;
  analysisById: Map<string, HotkeyRecordAnalysis>;
  onSelect: (id: string) => void;
};

export function HotkeyRecordsTable({
  rows,
  selectedId,
  analysisById,
  onSelect,
}: Props) {
  // A header sort applies over the toolbar's Sort select; its third click
  // returns to the select's order.
  const columns = useMemo<SortColumns<HotkeyRecord>>(() => ({
    name: r => r.name,
    key: r => formatKeyChord(r.key),
    command: r => r.command,
    compat: r => {
      const status = analysisById.get(r.id)?.status;
      return status ? HOTKEY_COMPAT_LABELS[status] : null;
    },
  }), [analysisById]);
  const { rows: sorted, sort, onSort } = useTableSort('hotkeys.das_records', rows, columns);
  return (
    <div className="hotkey-table-wrap">
      <table className="hotkey-table">
        <thead>
          <tr>
            <SortTh col="name" sort={sort} onSort={onSort}>NAME</SortTh>
            <SortTh col="key" sort={sort} onSort={onSort}>KEY</SortTh>
            <SortTh col="command" sort={sort} onSort={onSort}>Command(s)</SortTh>
            <SortTh col="compat" sort={sort} onSort={onSort}>Compatibility</SortTh>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const a = analysisById.get(r.id);
            const selectedRow = r.id === selectedId;
            return (
              <tr
                key={r.id}
                className={selectedRow ? 'selected' : undefined}
                onClick={() => onSelect(r.id)}
              >
                <td>{r.name}</td>
                <td>
                  <kbd>{formatKeyChord(r.key) || '—'}</kbd>
                </td>
                <td className="hotkey-cmd-cell" title={r.command}>
                  {r.command || '—'}
                </td>
                <td>
                  {a && (
                    <span className={`hotkey-badge hotkey-badge-${a.status}`}>
                      {HOTKEY_COMPAT_LABELS[a.status]}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="na-muted">
                No hotkeys yet — Import a .htk file or Add New Item.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
