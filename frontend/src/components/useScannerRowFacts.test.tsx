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

const bot = {
  session: { symbol_allowlist: ['grml', 'BRNQ', 'QNME'], trader_live: ['qnme'] },
  proposals: [],
  audit: [],
  error: null,
  errorSticky: false,
};
vi.mock('../bot/botSessionPoller', () => ({
  subscribeBotSession: () => () => {},
  getBotSessionSnapshot: () => bot,
}));

describe('useScannerRowFacts', () => {
  it('recording implies a held line; a live Trader tab this desk reported counts; otherwise quiet', () => {
    expect(renderHook(() => useScannerRowFacts('grml')).result.current).toEqual({
      recording: true, allowlisted: true, depthHeld: true,
    });
    expect(renderHook(() => useScannerRowFacts('QNME')).result.current).toEqual({
      recording: false, allowlisted: true, depthHeld: true,
    });
    expect(renderHook(() => useScannerRowFacts('BRNQ')).result.current).toEqual({
      recording: false, allowlisted: true, depthHeld: false,
    });
    expect(renderHook(() => useScannerRowFacts('ZZZZ')).result.current).toEqual({
      recording: false, allowlisted: false, depthHeld: false,
    });
  });
});
