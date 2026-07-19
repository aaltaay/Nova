/**
 * Local profile state for the DAS-compatible hotkey manager.
 * Imported records are never registered with useHotkeys.
 */

import { useCallback, useMemo, useState } from 'react';
import {
  analyzeProfile,
  summarizeAnalyses,
  type CompatSummary,
} from './compatibility';
import { createEmptyRecord, parseHtk, serializeHtk } from './htkFormat';
import {
  createEmptyProfile,
  loadProfile,
  profileFromRecords,
  restoreDefaultNovaActions,
  saveProfile,
} from './hotkeyStorage';
import type { NovaActionRecord } from './novaActionTypes';
import type {
  HotkeyProfile,
  HotkeyRecord,
  HotkeyRecordAnalysis,
  HtkParseIssue,
} from './types';
import { useHotkeyDispatchOptional } from './HotkeyDispatchContext';

export interface ImportPreview {
  fileName: string;
  records: HotkeyRecord[];
  issues: HtkParseIssue[];
}

function commit(next: HotkeyProfile): HotkeyProfile {
  saveProfile(next);
  return next;
}

export function useHotkeyProfile() {
  const [profile, setProfile] = useState<HotkeyProfile>(() => loadProfile());
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const dispatch = useHotkeyDispatchOptional();

  const analyses = useMemo(
    () => analyzeProfile(profile.records),
    [profile.records],
  );
  const analysisById = useMemo(() => {
    const map = new Map<string, HotkeyRecordAnalysis>();
    for (const a of analyses) map.set(a.recordId, a);
    return map;
  }, [analyses]);
  const summary: CompatSummary = useMemo(
    () => summarizeAnalyses(analyses),
    [analyses],
  );

  const previewImport = useCallback((text: string, fileName: string) => {
    const { records, issues } = parseHtk(text);
    setImportPreview({ fileName, records, issues });
  }, []);

  const cancelImport = useCallback(() => setImportPreview(null), []);

  const confirmImportReplace = useCallback(() => {
    setImportPreview((prev) => {
      if (!prev) return null;
      setProfile((cur) => {
        const next = commit(
          profileFromRecords(prev.records, prev.fileName, cur.novaActions, {
            automationBindings: cur.automationBindings,
            shortcutsMenuKey: cur.shortcutsMenuKey,
          }),
        );
        setSelectedId(prev.records[0]?.id ?? null);
        return next;
      });
      return null;
    });
  }, []);

  const exportText = useCallback(
    () => serializeHtk(profile.records),
    [profile.records],
  );

  const addRecord = useCallback(() => {
    const rec = createEmptyRecord();
    setProfile((prev) =>
      commit({
        ...prev,
        records: [...prev.records, rec],
        updatedAt: new Date().toISOString(),
      }),
    );
    setSelectedId(rec.id);
    return rec;
  }, []);

  const updateRecord = useCallback(
    (id: string, patch: Partial<HotkeyRecord>) => {
      setProfile((prev) => {
        const records = prev.records.map((r) => {
          if (r.id !== id) return r;
          const next = { ...r, ...patch };
          if (patch.command !== undefined && patch.command !== r.command) {
            next.commandEdited = true;
          }
          return next;
        });
        return commit({
          ...prev,
          records,
          updatedAt: new Date().toISOString(),
        });
      });
    },
    [],
  );

  const deleteRecord = useCallback((id: string) => {
    setProfile((prev) => {
      const records = prev.records.filter((r) => r.id !== id);
      setSelectedId((cur) => (cur === id ? records[0]?.id ?? null : cur));
      return commit({
        ...prev,
        records,
        updatedAt: new Date().toISOString(),
      });
    });
  }, []);

  const deleteKey = useCallback(
    (id: string) => {
      updateRecord(id, { key: { label: '', key: '' } });
    },
    [updateRecord],
  );

  const resetProfile = useCallback(() => {
    setProfile(commit(createEmptyProfile()));
    setSelectedId(null);
    dispatch?.reloadNovaActions();
  }, [dispatch]);

  const setNovaActions = useCallback((novaActions: NovaActionRecord[]) => {
    setProfile((prev) => {
      const next = commit({
        ...prev,
        novaActions,
        updatedAt: new Date().toISOString(),
      });
      dispatch?.reloadNovaActions();
      return next;
    });
  }, [dispatch]);

  const restoreNovaDefaults = useCallback(() => {
    setProfile((prev) => {
      const next = commit(restoreDefaultNovaActions(prev));
      dispatch?.reloadNovaActions();
      return next;
    });
  }, [dispatch]);

  return {
    profile,
    analyses,
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
    resetProfile,
    setNovaActions,
    restoreNovaDefaults,
  };
}
