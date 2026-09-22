/**
 * The three facts a scanner row's marks and hover actions state, read from
 * the stores that already own them:
 *
 *  - recording   -- fresh /api/ibkr/status `capture_symbols` (sessionRecordStore)
 *  - allowlisted -- the bot session's `symbol_allowlist`
 *  - depthHeld   -- the closest fact this window has to the backend's
 *                   `holds_depth_line`: a recording symbol (Session Record
 *                   holds its line) or a symbol this desk reported as a live
 *                   Trader tab (`trader_live`). The backend's own answer is
 *                   not on any status payload, so a line another window
 *                   holds is not known here -- the mark stays hollow and its
 *                   title says so.
 */
import { useSyncExternalStore } from 'react';
import { getBotSessionSnapshot, subscribeBotSession } from '../bot/botSessionPoller';
import { isTabRecording, subscribeSessionRecord } from '../capture/sessionRecordStore';

const EMPTY_BOT = { session: null, proposals: [], audit: [], error: null, errorSticky: false };

export interface ScannerRowFacts {
  recording: boolean;
  allowlisted: boolean;
  depthHeld: boolean;
}

function has(list: readonly string[] | undefined, sym: string): boolean {
  return (list ?? []).some((s) => String(s).trim().toUpperCase() === sym);
}

export function useScannerRowFacts(symbol: string): ScannerRowFacts {
  const sym = symbol.trim().toUpperCase();
  const recording = useSyncExternalStore(
    subscribeSessionRecord,
    () => isTabRecording(sym),
    () => false,
  );
  const bot = useSyncExternalStore(subscribeBotSession, getBotSessionSnapshot, () => EMPTY_BOT);
  const allowlisted = has(bot.session?.symbol_allowlist, sym);
  const traderLive = has(bot.session?.trader_live, sym);
  return { recording, allowlisted, depthHeld: recording || traderLive };
}
