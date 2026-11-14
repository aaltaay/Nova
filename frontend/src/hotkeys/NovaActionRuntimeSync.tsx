/**
 * Keeps Nova Action runtime (symbol / connection / position) in sync for the
 * shell-level hotkey dispatcher.
 */

import { useEffect } from 'react';
import { useIbkrStatus, useOthersHold } from '../ibkr';
import type { IbkrPosition } from '../ibkr';
import { useHotkeyDispatchOptional } from './HotkeyDispatchContext';

interface Props {
  symbol: string | null;
  position?: IbkrPosition | null;
  accountError?: string | null;
}

export function NovaActionRuntimeSync({
  symbol,
  position = null,
  accountError = null,
}: Props) {
  const dispatch = useHotkeyDispatchOptional();
  const status = useIbkrStatus();
  const othersHold = useOthersHold(symbol);

  useEffect(() => {
    if (!dispatch) return;
    dispatch.setRuntime({
      symbol: symbol ? symbol.toUpperCase() : null,
      connected: Boolean(status.connected),
      spendStatus: status.spend_status,
      accountMode: status.mode,
      accountError,
      position,
      othersHold,
    });
  }, [
    dispatch,
    symbol,
    position,
    othersHold,
    accountError,
    status.connected,
    status.spend_status,
    status.mode,
  ]);

  return null;
}
