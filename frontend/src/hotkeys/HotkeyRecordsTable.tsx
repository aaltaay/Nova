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
  return (
    <div className="hotkey-table-wrap">
      <table className="hotkey-table">
        <thead>
          <tr>
            <th>NAME</th>
            <th>KEY</th>
            <th>Command(s)</th>
            <th>Compatibility</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
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
