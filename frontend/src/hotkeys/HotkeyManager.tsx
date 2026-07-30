/**
 * Settings → Hot Keys landing (Webull-style shell).
 * Opens Hotkeys Settings manager; DAS import stays under Advanced.
 */

import { useMemo, useState } from 'react';
import {
  HOTKEYS_LANDING_SUBTITLE,
  HOTKEYS_LANDING_TITLE,
  HOTKEYS_SETTINGS_CTA,
  HOTKEYS_SETTINGS_RESET,
  HOTKEYS_TAB_CHART,
  HOTKEYS_TAB_GENERAL,
  HOTKEYS_TAB_PAPER,
  HOTKEYS_TAB_SOON,
  HOTKEYS_TAB_TRADE,
} from '../constants';
import { HotkeyHelpCatalog } from './HotkeyHelpCatalog';
import { HotkeysDasAdvanced } from './HotkeysDasAdvanced';
import { HotkeysLandingList } from './HotkeysLandingList';
import { HotkeysSettingsDialog } from './HotkeysSettingsDialog';
import { formatKeyChord } from './htkFormat';
import { NovaActiveShortcuts } from './NovaActiveShortcuts';
import type { HotkeySortKey } from './HotkeyFilterToolbar';
import { useHotkeyProfile } from './useHotkeyProfile';
import type { HotkeyCompatStatus } from './types';

type LandingTab = 'trade' | 'general' | 'paper' | 'chart';

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

  const [tab, setTab] = useState<LandingTab>('trade');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsFocusId, setSettingsFocusId] = useState<string | null>(null);
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

  function openSettings(focusId?: string | null) {
    setSettingsFocusId(focusId ?? null);
    setSettingsOpen(true);
  }

  if (showHelp) {
    return <HotkeyHelpCatalog onClose={() => setShowHelp(false)} />;
  }

  return (
    <div className="hotkey-manager panel settings-panel hk-landing" data-testid="hotkeys-landing">
      <h2 className="panel-title">{HOTKEYS_LANDING_TITLE}</h2>
      <p className="hk-landing-subtitle">{HOTKEYS_LANDING_SUBTITLE}</p>

      <div className="hk-landing-tabs" role="tablist" aria-label="Hot key categories">
        {(
          [
            ['trade', HOTKEYS_TAB_TRADE],
            ['general', HOTKEYS_TAB_GENERAL],
            ['paper', HOTKEYS_TAB_PAPER],
            ['chart', HOTKEYS_TAB_CHART],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`hk-landing-tab${tab === id ? ' is-active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'trade' ? (
        <>
          <div className="hk-landing-cta-row">
            <button
              type="button"
              className="btn-primary"
              data-testid="hotkeys-settings-cta"
              onClick={() => openSettings(null)}
            >
              {HOTKEYS_SETTINGS_CTA}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={restoreNovaDefaults}
            >
              {HOTKEYS_SETTINGS_RESET}
            </button>
          </div>

          <HotkeysLandingList
            actions={profile.novaActions}
            onOpenAction={(id) => openSettings(id)}
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
        </>
      ) : (
        <p className="na-muted" data-testid="hotkeys-tab-soon">{HOTKEYS_TAB_SOON}</p>
      )}

      {settingsOpen && (
        <HotkeysSettingsDialog
          actions={profile.novaActions}
          initialSelectedId={settingsFocusId}
          onChange={setNovaActions}
          onRestoreDefaults={restoreNovaDefaults}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
