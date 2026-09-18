import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { postBotAllowlist } from './api';
import {
  getBotSessionSnapshot,
  refreshBotSessionNow,
  runBotSessionWrite,
  setBotSessionError,
  subscribeBotSession,
} from './botSessionPoller';

const EMPTY = {
  session: null,
  proposals: [],
  audit: [],
  error: null,
  errorSticky: false,
};

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

  const add = useCallback(async (symbol: string) => {
    try {
      return await runBotSessionWrite(() => postBotAllowlist(symbol, 'add'));
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'allowlist add failed');
      return null;
    }
  }, []);

  const remove = useCallback(async (symbol: string) => {
    try {
      return await runBotSessionWrite(() => postBotAllowlist(symbol, 'remove'));
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'allowlist remove failed');
      return null;
    }
  }, []);

  return { symbols, isAllowed, add, remove, refresh: refreshBotSessionNow };
}
