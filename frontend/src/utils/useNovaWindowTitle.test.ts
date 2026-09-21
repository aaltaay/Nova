/**
 * @vitest-environment jsdom
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  formatScannerWindowTitle,
  formatTraderDocumentTitle,
  withRecording,
} from '../../electron/appTitle.mjs';

const record = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  return {
    symbols: [] as string[],
    listeners,
    set(symbols: string[]) { record.symbols = symbols; listeners.forEach(fn => fn()); },
  };
});
vi.mock('../capture/sessionRecordStore', () => ({
  getRecordingSymbols: () => record.symbols,
  subscribeSessionRecord: (listener: () => void) => {
    record.listeners.add(listener);
    return () => record.listeners.delete(listener);
  },
}));
import { novaRendererReleaseTag } from './novaReleaseTag';
import { useNovaDeskWindowTitle, useNovaWindowTitle } from './useNovaWindowTitle';

// VERSION is a build artifact (#344), so this asserts the tag vite injected --
// resolved from the generated file or from git -- rather than reading a repo file.
describe('useNovaWindowTitle', () => {
  it('writes a real VERSION tag onto scanner and trader titles', () => {
    const tag = novaRendererReleaseTag();
    expect(tag).toMatch(/^v\d+$/);

    const { rerender } = renderHook(
      ({ active, symbol }: { active: boolean; symbol: string | null }) =>
        useNovaWindowTitle(active, symbol),
      { initialProps: { active: false, symbol: null } },
    );
    expect(document.title).toBe(formatScannerWindowTitle(tag));

    rerender({ active: true, symbol: 'AAPL' });
    expect(document.title).toBe(formatTraderDocumentTitle('AAPL', tag));
  });

  it('leads with REC while a recording runs, on any view', () => {
    const tag = novaRendererReleaseTag();
    const { rerender } = renderHook(
      ({ active, symbol }: { active: boolean; symbol: string | null }) =>
        useNovaWindowTitle(active, symbol),
      { initialProps: { active: false, symbol: null } },
    );
    act(() => record.set(['GRML']));
    expect(document.title).toBe(withRecording(formatScannerWindowTitle(tag), 'GRML'));
    expect(document.title.startsWith('● REC GRML')).toBe(true);
    rerender({ active: true, symbol: 'AAPL' });
    expect(document.title).toBe(withRecording(formatTraderDocumentTitle('AAPL', tag), 'GRML'));
    act(() => record.set([]));
    expect(document.title).toBe(formatTraderDocumentTitle('AAPL', tag));
  });

  it('sets a sample trader title from ?view=sample&symbol=SMPL', () => {
    const tag = novaRendererReleaseTag();
    window.history.replaceState({}, '', '/?view=sample&symbol=SMPL');
    renderHook(() => useNovaDeskWindowTitle(true, false, null));
    expect(document.title).toBe(formatTraderDocumentTitle('SMPL', tag));
  });
});
