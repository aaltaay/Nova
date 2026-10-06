/** Request-local live REST fencing and newer served halt evidence (#764). */
import type { Dispatch, SetStateAction } from 'react';
import { SCANNER_LIVE_REQUEST_HALT_MAX_SYMBOLS } from '../constantGroups/scanner_board';
import type { ScannerRow } from '../types/scanner';
import { applyScannerHaltPatch, type ScannerHaltRow } from './scannerHaltPatch';
import type { ScannerRestSink } from './scannerRestApply';

export type ScannerLiveRequest = {
  sink: ScannerRestSink;
  isCurrent: () => boolean;
  overflowed: () => boolean;
  finish: () => void;
};

function stateValue<T>(action: SetStateAction<T>, previous: T): T {
  return typeof action === 'function' ? (action as (value: T) => T)(previous) : action;
}

/** One pending request, no receipts retained after it finishes or loses scope. */
export function createScannerLiveRequestScope() {
  let view = '';
  let liveIbkr = false;
  let scope = {};
  let latestRequest = {};
  let pending: { record: (rows: ScannerHaltRow[]) => void; cancel: () => void } | null = null;

  const invalidate = () => {
    scope = {};
    pending?.cancel();
    pending = null;
  };

  return {
    setView(historyDate: string | null, provider: string, persistent: boolean) {
      const next = JSON.stringify([historyDate, provider, persistent]);
      if (next === view) return;
      view = next;
      liveIbkr = historyDate === null && provider === 'ibkr';
      invalidate();
    },
    invalidate,
    capture: () => scope,
    isScope: (captured: object) => captured === scope,
    acceptsHalt: () => liveIbkr,
    recordHalt: (rows: ScannerHaltRow[]) => { if (liveIbkr) pending?.record(rows); },
    begin(sink: ScannerRestSink, signal: AbortSignal): ScannerLiveRequest {
      pending?.cancel();
      const requestScope = scope;
      const identity = {};
      latestRequest = identity;
      const receipts = new Map<string, ScannerHaltRow>();
      let cancelled = signal.aborted;
      let overflow = false;
      let finished = false;
      // A current-view timeout still owns its failure/retry; only its rows stop applying.
      const isCurrent = () => requestScope === scope && identity === latestRequest;
      const canApply = () => isCurrent() && !cancelled && !overflow;
      const cancel = () => { cancelled = true; receipts.clear(); signal.removeEventListener('abort', cancel); };

      const guard = <T>(setter: Dispatch<SetStateAction<T>>): Dispatch<SetStateAction<T>> => action => {
        if (canApply()) setter(previous => canApply() ? stateValue(action, previous) : previous);
      };
      const guardRows = (setter: ScannerRestSink['setGappers']): ScannerRestSink['setGappers'] => action => {
        if (!canApply()) return;
        // React may evaluate this updater after finish clears the mutable map.
        const snapshot = [...receipts.values()];
        setter(previous => canApply()
          ? applyScannerHaltPatch<ScannerRow>(stateValue(action, previous), snapshot)
          : previous);
      };
      const entry = {
        cancel,
        record(rows: ScannerHaltRow[]) {
          if (!canApply() || finished) return;
          for (const row of rows) {
            const symbol = row.symbol.trim().toUpperCase();
            if (!receipts.has(symbol) && receipts.size >= SCANNER_LIVE_REQUEST_HALT_MAX_SYMBOLS) {
              // Incomplete evidence must not allow an older REST value to win.
              overflow = true;
              receipts.clear();
              return;
            }
            receipts.set(symbol, { symbol, halted: row.halted });
          }
        },
      };
      pending = entry;
      signal.addEventListener('abort', cancel, { once: true });

      return {
        isCurrent,
        overflowed: () => overflow,
        sink: {
          applyEnvelope: data => { if (canApply()) sink.applyEnvelope(data); },
          setGappers: guardRows(sink.setGappers),
          setGainers: guardRows(sink.setGainers),
          setLosers: guardRows(sink.setLosers),
          setAfterhours: guardRows(sink.setAfterhours),
          setLargeCap: guardRows(sink.setLargeCap),
          setLastGood: guard(sink.setLastGood),
          setTableMeta: guard(sink.setTableMeta),
          setScanAges: guard(sink.setScanAges),
        },
        finish() {
          finished = true;
          receipts.clear();
          signal.removeEventListener('abort', cancel);
          if (pending === entry) pending = null;
        },
      };
    },
  };
}
