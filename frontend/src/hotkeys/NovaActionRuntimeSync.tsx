/**
 * Keeps Nova Action runtime (symbol / connection / position) in sync for the
 * shell-level hotkey dispatcher.
 */

import { useEffect } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { IbkrPosition } from '../ibkr/types';
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

  useEffect(() => {
    if (!dispatch) return;
    dispatch.setRuntime({
      symbol: symbol ? symbol.toUpperCase() : null,
      connected: Boolean(status.connected),
      spendStatus: status.spend_status,
      accountError,
      position,
    });
  }, [
    dispatch,
    symbol,
    position,
    accountError,
    status.connected,
    status.spend_status,
  ]);

  return null;
}
