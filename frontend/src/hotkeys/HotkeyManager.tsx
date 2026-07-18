/**
 * DAS-style Name / Key / Command manager.
 * Import/export .htk, edit, analyze — never execute imported commands.
 */

import { useMemo, useRef, useState } from 'react';
import { HOTKEY_MANAGER_INACTIVE_BANNER } from '../constants';
import { HotkeyFileToolbar } from './HotkeyFileToolbar';
import { HotkeyFilterToolbar, type HotkeySortKey } from './HotkeyFilterToolbar';
import { HotkeyHelpCatalog } from './HotkeyHelpCatalog';
import { HotkeyImportPreview } from './HotkeyImportPreview';
import { HotkeyItemActions } from './HotkeyItemActions';
import { HotkeyRecordsTable } from './HotkeyRecordsTable';
import { HotkeyRowEditor } from './HotkeyRowEditor';
import { HotkeySelectedDetail } from './HotkeySelectedDetail';
import { HotkeySummaryBar } from './HotkeySummaryBar';
import { NovaActionsTable } from './NovaActionsTable';
import { NovaActiveShortcuts } from './NovaActiveShortcuts';
import { formatKeyChord } from './htkFormat';
import { useHotkeyProfile } from './useHotkeyProfile';
import type { HotkeyCompatStatus, HotkeyRecord } from './types';

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
    setNovaActions,
    restoreNovaDefaults,
  } = useHotkeyProfile();

  const fileRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<HotkeySortKey>('name');
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

      <HotkeySummaryBar summary={summary} />

      <HotkeyFileToolbar
        fileName={profile.fileName}
        fileRef={fileRef}
        onImportFile={(f) => void onImportFile(f)}
        onExport={onExport}
        onHelp={() => setShowHelp(true)}
      />

      <HotkeyFilterToolbar
        query={query}
        onQuery={setQuery}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        sortKey={sortKey}
        onSortKey={setSortKey}
      />

      <HotkeyRecordsTable
        rows={rows}
        selectedId={selectedId}
        analysisById={analysisById}
        onSelect={setSelectedId}
      />

      <HotkeyItemActions
        selected={selected}
        onEdit={() => selected && setEditing(selected)}
        onAdd={() => {
          const rec = addRecord();
          setEditing(rec);
        }}
        onDeleteItem={() => selected && deleteRecord(selected.id)}
        onDeleteKey={() => selected && deleteKey(selected.id)}
      />

      {selectedAnalysis && selected && (
        <HotkeySelectedDetail selected={selected} analysis={selectedAnalysis} />
      )}

      <NovaActionsTable
        actions={profile.novaActions}
        onChange={setNovaActions}
        onRestoreDefaults={restoreNovaDefaults}
      />

      <NovaActiveShortcuts />

      {importPreview && (
        <HotkeyImportPreview
          preview={importPreview}
          onConfirm={confirmImportReplace}
          onCancel={cancelImport}
        />
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
