/**
 * Shared position + gate snapshot for both chart flatten entry points
 * (Long/Short tag menu and the right-click menu), so the two cannot drift on
 * connected / spend / stale-account rules.
 */
import { CLOSE_POSITION_ACCOUNT_ERROR_TITLE, CLOSE_POSITION_STALE_WHY } from '../constants';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import type { IbkrMode, IbkrPosition } from '../ibkr/types';
import { findOpenIbkrPosition } from './positionOverlay';

export interface ChartPositionContext {
  position: IbkrPosition | null;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  flattenDisabled: boolean;
  /** Why `flattenDisabled` is set (ux/whyTip.ts); null while it is not. */
  flattenWhy: string | null;
}

export function useChartPositionContext(symbol: string): ChartPositionContext {
  const account = useOptionalIbkrAccountContext();
  const status = useIbkrStatus();
  const position = findOpenIbkrPosition(account?.positions ?? [], symbol) ?? null;
  const mode: IbkrMode =
    status.mode === 'live'
      ? 'live'
      : status.mode === 'sim'
        ? 'sim'
        : status.mode === 'disconnected'
          ? 'disconnected'
          : 'paper';
  return {
    position,
    mode,
    connected: Boolean(status.connected) && !account?.stale,
    spendStatus: status.spend_status,
    flattenDisabled: Boolean(account?.error || account?.stale),
    flattenWhy: account?.stale
      ? CLOSE_POSITION_STALE_WHY
      : account?.error
        ? CLOSE_POSITION_ACCOUNT_ERROR_TITLE
        : null,
  };
}
