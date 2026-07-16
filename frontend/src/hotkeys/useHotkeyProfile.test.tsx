/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOTKEY_STORAGE_KEY } from './hotkeyStorage';
import { useHotkeyProfile } from './useHotkeyProfile';

type Api = ReturnType<typeof useHotkeyProfile>;
let latest: Api | null = null;

function Probe() {
  latest = useHotkeyProfile();
  return null;
}

describe('useHotkeyProfile', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function mount() {
    act(() => {
      root.render(<Probe />);
    });
  }

  it('adds, updates, deletes records and persists locally', () => {
    mount();
    expect(latest).toBeTruthy();
    let recId = '';
    act(() => {
      const rec = latest!.addRecord();
      recId = rec.id;
    });
    act(() => {
      latest!.updateRecord(recId, {
        name: 'Sell Half',
        key: { label: 'F8', key: 'F8' },
        command: 'ROUTE=MARKET;Share=Pos*0.5;SELL=Send',
      });
    });
    expect(latest!.profile.records.some((r) => r.name === 'Sell Half')).toBe(true);
    const stored = localStorage.getItem(HOTKEY_STORAGE_KEY);
    expect(stored).toContain('Sell Half');
    expect(latest!.analysisById.get(recId)?.status).toBe('translatable_later');

    act(() => {
      latest!.deleteRecord(recId);
    });
    expect(latest!.profile.records.find((r) => r.id === recId)).toBeUndefined();
  });

  it('import preview is non-destructive until confirm', () => {
    mount();
    act(() => {
      latest!.addRecord();
    });
    const before = latest!.profile.records.length;
    act(() => {
      latest!.previewImport('F9:Panic:CXL ALLSYMB\n', 'import.htk');
    });
    expect(latest!.importPreview?.records).toHaveLength(1);
    expect(latest!.profile.records.length).toBe(before);
    act(() => {
      latest!.confirmImportReplace();
    });
    expect(latest!.profile.fileName).toBe('import.htk');
    expect(latest!.profile.records).toHaveLength(1);
    expect(latest!.profile.records[0].name).toBe('Panic');
  });

  it('exportText round-trips without registering keydown listeners', () => {
    const addListener = vi.spyOn(window, 'addEventListener');
    mount();
    act(() => {
      const rec = latest!.addRecord();
      latest!.updateRecord(rec.id, {
        name: 'Buy',
        key: { label: 'F1', key: 'F1' },
        command: 'ROUTE=MARKET;Share=1;BUY=Send',
      });
    });
    const text = latest!.exportText();
    expect(text).toContain('F1:Buy:');
    expect(text).toContain('BUY=Send');
    const keydownRegs = addListener.mock.calls.filter((c) => c[0] === 'keydown');
    expect(keydownRegs).toHaveLength(0);
  });
});
