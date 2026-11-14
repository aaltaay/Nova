/**
 * The fact a scanner row's marks and hover actions state, read from the store
 * that already owns it:
 *
 *  - recording -- fresh /api/ibkr/status `capture_symbols` (sessionRecordStore)
 *
 * The bot's allowlist and its depth-line mark are gone: the strategies only
 * watch and never trade (ADR 072).
 */
import { useSyncExternalStore } from 'react';
import { isTabRecording, subscribeSessionRecord } from '../capture/sessionRecordStore';

export interface ScannerRowFacts {
  recording: boolean;
}

export function useScannerRowFacts(symbol: string): ScannerRowFacts {
  const sym = symbol.trim().toUpperCase();
  const recording = useSyncExternalStore(
    subscribeSessionRecord,
    () => isTabRecording(sym),
    () => false,
  );
  return { recording };
}
