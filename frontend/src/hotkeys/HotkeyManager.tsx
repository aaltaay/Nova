/**
 * DAS-style Name / Key / Command manager.
 * Import/export .htk, edit, analyze — never execute imported commands.
 */

import { useMemo, useRef, useState } from 'react';
import { HOTKEY_MANAGER_INACTIVE_BANNER } from '../constants';
import { HotkeyHelpCatalog } from './HotkeyHelpCatalog';
import { HotkeyRowEditor } from './HotkeyRowEditor';
import { NovaActiveShortcuts } from './NovaActiveShortcuts';
import { formatKeyChord } from './htkFormat';
import { useHotkeyProfile } from './useHotkeyProfile';
import {
  HOTKEY_COMPAT_LABELS,
  HOTKEY_EVIDENCE_LABELS,
  type HotkeyCompatStatus,
  type HotkeyRecord,
} from './types';

type SortKey = 'name' | 'key' | 'status';

export function HotkeyManager() {
  const {
    profile,
    analysisById,
    summary,
    selectedId,
    setSelectedId,
    importPreview,
    previewImport,
    cancelImport,
    confirmImportReplace,
    exportText,
    addRecord,
    updateRecord,
    deleteRecord,
    deleteKey,
  } = useHotkeyProfile();

  const fileRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [editing, setEditing] = useState<HotkeyRecord | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [statusFilter, setStatusFilter] = useState<HotkeyCompatStatus | 'all'>('all');

  const selected = profile.records.find((r) => r.id === selectedId) ?? null;
  const selectedAnalysis = selected ? analysisById.get(selected.id) : undefined;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = [...profile.records];
    if (statusFilter !== 'all') {
      list = list.filter((r) => analysisById.get(r.id)?.status === statusFilter);
    }
    if (q) {
      list = list.filter(
        (r) =>
          r.name.toLowerCase().includes(q)
          || formatKeyChord(r.key).toLowerCase().includes(q)
          || r.command.toLowerCase().includes(q),
      );
    }
    list.sort((a, b) => {
      if (sortKey === 'key') {
        return formatKeyChord(a.key).localeCompare(formatKeyChord(b.key));
      }
      if (sortKey === 'status') {
        const sa = analysisById.get(a.id)?.status ?? '';
        const sb = analysisById.get(b.id)?.status ?? '';
        return sa.localeCompare(sb);
      }
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [profile.records, query, sortKey, statusFilter, analysisById]);

  const onImportFile = async (file: File) => {
    const text = await file.text();
    previewImport(text, file.name || 'hotkey.htk');
  };

  const onExport = () => {
    const blob = new Blob([exportText()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = profile.fileName.endsWith('.htk')
      ? profile.fileName
      : `${profile.fileName}.htk`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (showHelp) {
    return <HotkeyHelpCatalog onClose={() => setShowHelp(false)} />;
  }

  return (
    <div className="hotkey-manager panel settings-panel">
      <h2 className="panel-title">Hotkeys</h2>

      <div className="hotkey-inactive-banner" role="status">
        {HOTKEY_MANAGER_INACTIVE_BANNER}
      </div>

      <div className="hotkey-summary">
        <span>Translatable: {summary.translatable_later}</span>
        <span>Backend: {summary.backend_required}</span>
        <span>DAS-specific: {summary.das_ibkr_specific}</span>
        <span>Invalid: {summary.invalid_unsafe}</span>
        <span>Conflicts: {summary.conflicts}</span>
      </div>

      <div className="hotkey-file-row">
        <label>
          HotKey File
          <input type="text" value={profile.fileName} readOnly aria-label="Hotkey file name" />
        </label>
        <input
          ref={fileRef}
          type="file"
          accept=".htk,text/plain"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onImportFile(f);
            e.target.value = '';
          }}
        />
        <button type="button" className="btn-secondary" onClick={() => fileRef.current?.click()}>
          Import…
        </button>
        <button type="button" className="btn-secondary" onClick={onExport}>
          Export
        </button>
        <button type="button" className="btn-secondary" onClick={() => setShowHelp(true)}>
          Help
        </button>
      </div>

      <div className="hotkey-toolbar">
        <input
          type="search"
          placeholder="Search name, key, command…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search hotkeys"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as HotkeyCompatStatus | 'all')}
          aria-label="Filter by compatibility"
        >
          <option value="all">All statuses</option>
          {(Object.keys(HOTKEY_COMPAT_LABELS) as HotkeyCompatStatus[]).map((s) => (
            <option key={s} value={s}>
              {HOTKEY_COMPAT_LABELS[s]}
            </option>
          ))}
        </select>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          aria-label="Sort hotkeys"
        >
          <option value="name">Sort: Name</option>
          <option value="key">Sort: Key</option>
          <option value="status">Sort: Compatibility</option>
        </select>
      </div>

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
                  onClick={() => setSelectedId(r.id)}
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

      <div className="hotkey-actions">
        <button
          type="button"
          disabled={!selected}
          onClick={() => selected && setEditing(selected)}
        >
          Edit Item
        </button>
        <button
          type="button"
          onClick={() => {
            const rec = addRecord();
            setEditing(rec);
          }}
        >
          Add New Item
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!selected}
          onClick={() => selected && deleteRecord(selected.id)}
        >
          Delete Item
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!selected}
          onClick={() => selected && deleteKey(selected.id)}
        >
          Delete Key
        </button>
      </div>

      {selectedAnalysis && selected && (
        <div className="hotkey-detail">
          <h4 className="nova-os-section-title">Selected: {selected.name}</h4>
          <p className="na-muted">
            Evidence: {HOTKEY_EVIDENCE_LABELS[selectedAnalysis.evidence]}
          </p>
          {selectedAnalysis.diagnostics.length > 0 ? (
            <ul>
              {selectedAnalysis.diagnostics.map((d) => (
                <li key={`${d.code}-${d.message}`}>{d.message}</li>
              ))}
            </ul>
          ) : (
            <p className="na-muted">No diagnostics.</p>
          )}
        </div>
      )}

      <NovaActiveShortcuts />

      {importPreview && (
        <div className="hotkey-import-preview" role="dialog" aria-label="Import preview">
          <h4 className="nova-os-section-title">Import preview — {importPreview.fileName}</h4>
          <p>
            {importPreview.records.length} record(s)
            {importPreview.issues.length > 0
              && `, ${importPreview.issues.length} parse issue(s)`}
            . Replace the current profile?
          </p>
          {importPreview.issues.length > 0 && (
            <ul>
              {importPreview.issues.slice(0, 8).map((iss) => (
                <li key={`${iss.line}-${iss.message}`}>
                  Line {iss.line}: {iss.message}
                </li>
              ))}
            </ul>
          )}
          <div className="form-row">
            <button type="button" onClick={confirmImportReplace}>
              Replace profile
            </button>
            <button type="button" className="btn-secondary" onClick={cancelImport}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {editing && (
        <HotkeyRowEditor
          record={editing}
          onSave={(patch) => {
            updateRecord(editing.id, patch);
            setEditing(null);
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}
