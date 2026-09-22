/**
 * Settings > Hot Keys: the Nova Actions editor inline in the section, the
 * active automation shortcuts under it, and the DAS import under Advanced.
 */

import { useMemo, useState } from 'react';
import { HOTKEYS_SECTION_SUBTITLE, HOTKEYS_SECTION_TITLE } from '../constants';
import { HotkeyHelpCatalog } from './HotkeyHelpCatalog';
import { HotkeysDasAdvanced } from './HotkeysDasAdvanced';
import { HotkeysSettingsEditor } from './HotkeysSettingsEditor';
import { formatKeyChord } from './htkFormat';
import { NovaActiveShortcuts } from './NovaActiveShortcuts';
import type { HotkeySortKey } from './HotkeyFilterToolbar';
import { useHotkeyProfile } from './useHotkeyProfile';
import type { HotkeyCompatStatus } from './types';

export function HotkeyManager({ onDone }: { onDone?: () => void }) {
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
    deleteNovaAction,
  } = useHotkeyProfile();

  const [showHelp, setShowHelp] = useState(false);
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<HotkeySortKey>('name');
  const [statusFilter, setStatusFilter] = useState<HotkeyCompatStatus | 'all'>('all');

  const selected = profile.records.find((r) => r.id === selectedId) ?? null;
  const selectedAnalysis = selected ? analysisById.get(selected.id) : undefined;
  const mapDisabledReason = !selected ? 'Select a DAS row first' : null;

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
    <div className="hk-section" data-testid="hotkeys-section">
      <div className="hk-section-head">
        <h3 className="settings-block-title">{HOTKEYS_SECTION_TITLE}</h3>
        <p className="settings-block-hint">{HOTKEYS_SECTION_SUBTITLE}</p>
      </div>

      <HotkeysSettingsEditor
        actions={profile.novaActions}
        onChange={setNovaActions}
        onRestoreDefaults={restoreNovaDefaults}
        onDelete={deleteNovaAction}
        onDone={onDone}
      />

      <NovaActiveShortcuts />

      <HotkeysDasAdvanced
        profile={profile}
        summary={summary}
        rows={rows}
        selectedId={selectedId}
        setSelectedId={setSelectedId}
        analysisById={analysisById}
        selected={selected}
        selectedAnalysis={selectedAnalysis}
        mapDisabledReason={mapDisabledReason}
        importPreview={importPreview}
        onImportFile={(f) => void onImportFile(f)}
        onExport={onExport}
        onHelp={() => setShowHelp(true)}
        query={query}
        setQuery={setQuery}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        sortKey={sortKey}
        setSortKey={setSortKey}
        addRecord={addRecord}
        updateRecord={updateRecord}
        deleteRecord={deleteRecord}
        deleteKey={deleteKey}
        setNovaActions={setNovaActions}
        confirmImportReplace={confirmImportReplace}
        cancelImport={cancelImport}
      />
    </div>
  );
}
