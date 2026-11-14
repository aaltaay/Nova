/**
 * @vitest-environment jsdom
 */
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useScannerRowFacts } from './useScannerRowFacts';

const recording = new Set<string>(['GRML']);
vi.mock('../capture/sessionRecordStore', () => ({
  subscribeSessionRecord: () => () => {},
  isTabRecording: (s: string) => recording.has(s),
}));

describe('useScannerRowFacts', () => {
  it('says whether the symbol is recording, whatever its case', () => {
    expect(renderHook(() => useScannerRowFacts('grml')).result.current).toEqual({ recording: true });
    expect(renderHook(() => useScannerRowFacts('ZZZZ')).result.current).toEqual({ recording: false });
  });
});
