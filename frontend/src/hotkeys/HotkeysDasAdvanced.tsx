/**
 * Collapsed Advanced DAS import section on Hot Keys landing.
 */

import { useRef, useState } from 'react';
import {
  HOTKEY_MANAGER_INACTIVE_BANNER,
  HOTKEYS_ADVANCED_DAS_HINT,
  HOTKEYS_ADVANCED_DAS_TITLE,
} from '../constants';
import type { CompatSummary } from './compatibility';
import { HotkeyFileToolbar } from './HotkeyFileToolbar';
import { HotkeyFilterToolbar, type HotkeySortKey } from './HotkeyFilterToolbar';
import { HotkeyImportPreview } from './HotkeyImportPreview';
import { HotkeyItemActions } from './HotkeyItemActions';
import { HotkeyRecordsTable } from './HotkeyRecordsTable';
import { HotkeyRowEditor } from './HotkeyRowEditor';
import { HotkeySelectedDetail } from './HotkeySelectedDetail';
import { HotkeySummaryBar } from './HotkeySummaryBar';
import {
  buildMappedNovaAction,
  suggestNovaActionFromDas,
  type MapSuggestion,
} from './mapDasToNovaAction';
import { MapDasToNovaDialog } from './MapDasToNovaDialog';
import type { NovaActionRecord } from './novaActionTypes';
import type {
  HotkeyCompatStatus,
  HotkeyProfile,
  HotkeyRecord,
  HotkeyRecordAnalysis,
} from './types';
import type { ImportPreview } from './useHotkeyProfile';

export function HotkeysDasAdvanced({
  profile,
  summary,
  rows,
  selectedId,
  setSelectedId,
  analysisById,
  selected,
  selectedAnalysis,
  mapDisabledReason,
  importPreview,
  onImportFile,
  onExport,
  onHelp,
  query,
  setQuery,
  statusFilter,
  setStatusFilter,
  sortKey,
  setSortKey,
  addRecord,
  updateRecord,
  deleteRecord,
  deleteKey,
  setNovaActions,
  confirmImportReplace,
  cancelImport,
}: {
  profile: HotkeyProfile;
  summary: CompatSummary;
  rows: HotkeyRecord[];
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  analysisById: Map<string, HotkeyRecordAnalysis>;
  selected: HotkeyRecord | null;
  selectedAnalysis: HotkeyRecordAnalysis | undefined;
  mapDisabledReason: string | null;
  importPreview: ImportPreview | null;
  onImportFile: (f: File) => void;
  onExport: () => void;
  onHelp: () => void;
  query: string;
  setQuery: (q: string) => void;
  statusFilter: HotkeyCompatStatus | 'all';
  setStatusFilter: (s: HotkeyCompatStatus | 'all') => void;
  sortKey: HotkeySortKey;
  setSortKey: (k: HotkeySortKey) => void;
  addRecord: () => HotkeyRecord;
  updateRecord: (id: string, patch: Partial<HotkeyRecord>) => void;
  deleteRecord: (id: string) => void;
  deleteKey: (id: string) => void;
  setNovaActions: (next: NovaActionRecord[]) => void;
  confirmImportReplace: () => void;
  cancelImport: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<HotkeyRecord | null>(null);
  const [mapSuggestion, setMapSuggestion] = useState<Extract<MapSuggestion, { ok: true }> | null>(null);
  const [mapNotice, setMapNotice] = useState<string | null>(null);

  const selectedMapHint = selected
    ? suggestNovaActionFromDas(selected.command)
    : null;
  const resolvedMapDisabled = mapDisabledReason
    ?? (selectedMapHint && !selectedMapHint.ok ? selectedMapHint.reason : null);

  return (
    <details className="hk-advanced-das" data-testid="hotkeys-advanced-das">
      <summary className="hk-advanced-das-summary">{HOTKEYS_ADVANCED_DAS_TITLE}</summary>
      <p className="na-muted">{HOTKEYS_ADVANCED_DAS_HINT}</p>
      <div className="hotkey-inactive-banner" role="status">
        {HOTKEY_MANAGER_INACTIVE_BANNER}
      </div>
      <HotkeySummaryBar summary={summary} />
      <HotkeyFileToolbar
        fileName={profile.fileName}
        fileRef={fileRef}
        onImportFile={(f) => void onImportFile(f)}
        onExport={onExport}
        onHelp={onHelp}
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
        mapDisabledReason={resolvedMapDisabled}
        onMapToNova={() => {
          if (!selected || !selectedMapHint?.ok) return;
          setMapNotice(null);
          setMapSuggestion(selectedMapHint);
        }}
      />
      {mapNotice && <p className="na-muted" role="status">{mapNotice}</p>}
      {selectedAnalysis && selected && (
        <HotkeySelectedDetail selected={selected} analysis={selectedAnalysis} />
      )}
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
      {mapSuggestion && selected && (
        <MapDasToNovaDialog
          record={selected}
          suggestion={mapSuggestion}
          onCancel={() => setMapSuggestion(null)}
          onConfirm={() => {
            const mapped = buildMappedNovaAction(selected, mapSuggestion);
            setNovaActions([...profile.novaActions, mapped]);
            setMapSuggestion(null);
            setMapNotice(
              `Mapped "${mapped.name}" as a disabled Nova Action -- enable it in Hotkeys Settings.`,
            );
          }}
        />
      )}
    </details>
  );
}
