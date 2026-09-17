import { useCallback, useEffect, useState } from 'react';
import { fetchBotSession, postBotAllowlist } from './api';

export function useBotAllowlist() {
  const [symbols, setSymbols] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchBotSession();
      setSymbols(next.symbol_allowlist || []);
    } catch {
      /* menu stays empty until the next successful fetch */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const isAllowed = useCallback(
    (symbol: string) => symbols.includes(symbol.trim().toUpperCase()),
    [symbols],
  );

  const add = useCallback(async (symbol: string) => {
    const next = await postBotAllowlist(symbol, 'add');
    setSymbols(next.symbol_allowlist || []);
    return next;
  }, []);

  const remove = useCallback(async (symbol: string) => {
    const next = await postBotAllowlist(symbol, 'remove');
    setSymbols(next.symbol_allowlist || []);
    return next;
  }, []);

  return { symbols, isAllowed, add, remove, refresh };
}
