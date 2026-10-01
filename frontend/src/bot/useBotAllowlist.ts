/**
 * The bot's stocks on this venue (ADR 042 F): read from the bot session, changed
 * through `POST /api/bot/allowlist`, which goes through the stock-mode rules (the
 * Live lock, "you hold it", the 50-stock cap). A refusal is never silent: `toggle`
 * hands the backend's words to the caller, and `add` / `remove` -- which every
 * ticker list's button calls -- raise them as a notice in the window that asked.
 */
import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { botTradeRefusedTitle } from '../constantGroups/bot';
import { postBotAllowlist } from './api';
import { pushBotNotice } from './botNoticeStore';
import {
  getBotSessionSnapshot,
  refreshBotSessionNow,
  runBotSessionWrite,
  subscribeBotSession,
} from './botSessionPoller';
import type { BotSession } from './types';

const EMPTY = {
  session: null,
  proposals: [],
  audit: [],
  error: null,
  errorSticky: false,
};

export interface BotAllowlistAnswer {
  session: BotSession | null;
  /** The backend's refusal in its own words; null when it was done. */
  error: string | null;
}

/** Add or remove one stock; `quiet` leaves the refusal to the caller (it shows it in place). */
export async function toggleBotStock(symbol: string, op: 'add' | 'remove', quiet = false): Promise<BotAllowlistAnswer> {
  const sym = symbol.trim().toUpperCase();
  try {
    // The backend normalizes the symbol; it is sent as given.
    return { session: await runBotSessionWrite(() => postBotAllowlist(symbol.trim(), op)), error: null };
  } catch (err) {
    const error = err instanceof Error && err.message ? err.message : `Nova did not ${op} ${sym}`;
    if (!quiet) pushBotNotice({ tone: 'bad', title: botTradeRefusedTitle(sym, op === 'add'), text: error });
    return { session: null, error };
  }
}

export function useBotAllowlist() {
  const snap = useSyncExternalStore(
    subscribeBotSession,
    getBotSessionSnapshot,
    () => EMPTY,
  );
  const symbols = useMemo(
    () => snap.session?.symbol_allowlist ?? [],
    [snap.session?.symbol_allowlist],
  );

  const isAllowed = useCallback(
    (symbol: string) => symbols.includes(symbol.trim().toUpperCase()),
    [symbols],
  );

  const add = useCallback(async (symbol: string) => (await toggleBotStock(symbol, 'add')).session, []);
  const remove = useCallback(async (symbol: string) => (await toggleBotStock(symbol, 'remove')).session, []);

  return { symbols, isAllowed, add, remove, toggle: toggleBotStock, refresh: refreshBotSessionNow };
}
