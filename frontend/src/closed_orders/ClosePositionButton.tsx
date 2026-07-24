/**
 * Flatten / close full position — ADR 007 place path (not cancel-working-order).
 */
import { useState, type MouseEvent } from 'react';
import {
  APP_DIALOG_FLATTEN_LABEL,
  CLOSE_POSITION_ACCOUNT_ERROR_TITLE,
  CLOSE_POSITION_BUTTON_BUSY_LABEL,
  CLOSE_POSITION_BUTTON_LABEL,
  CLOSE_POSITION_NO_POSITION_TITLE,
  CLOSE_POSITION_VS_CANCEL_HINT,
  TICKER_TRADE_ORDER_DISCLOSURE,
} from '../constants';
import { captureBrowserAction } from '../execution_latency';
import { closeFullPosition } from '../ibkr/closeFullPosition';
import type { IbkrMode, IbkrPosition } from '../ibkr/types';
import { alertApp, confirmApp } from '../ux';
import { formatShareQty } from '../utils/formatShareQty';

interface Props {
  position: IbkrPosition;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  disabled?: boolean;
  onClosed?: () => void;
}

export function ClosePositionButton({
  position,
  mode,
  connected,
  spendStatus,
  disabled = false,
  onClosed,
}: Props) {
  const [busy, setBusy] = useState(false);
  const hasPosition = position.qty !== 0;
  const spendLocked =
    spendStatus === 'locked' || spendStatus === 'locked_live_unconfirmed';
  const canClose =
    connected && mode !== 'disconnected' && hasPosition && !spendLocked && !disabled && !busy;

  async function handleClick(e: MouseEvent) {
    e.stopPropagation();
    if (!canClose) return;
    const actionTiming = captureBrowserAction('user_action');
    const absQty = formatShareQty(Math.abs(position.qty));
    const closeSide = position.qty > 0 ? 'SELL' : 'BUY';
    const confirmed = await confirmApp({
      title: `Flatten ${position.symbol}?`,
      message:
        `${TICKER_TRADE_ORDER_DISCLOSURE}\n\n` +
        `${CLOSE_POSITION_VS_CANCEL_HINT}\n\n` +
        `Flatten ${absQty} shares of ${position.symbol} with a ${closeSide} market order ` +
        `on the ${mode.toUpperCase()} account?`,
      confirmLabel: APP_DIALOG_FLATTEN_LABEL,
      tone: 'danger',
    });
    if (!confirmed) return;
    setBusy(true);
    try {
      const res = await closeFullPosition(position.symbol, position.qty, {
        timingAction: actionTiming,
        referencePrice: position.market_price,
      });
      if (res.ok) onClosed?.();
      else await alertApp({ title: 'Flatten failed', message: res.error, tone: 'danger' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      className="ibkr-flatten-btn"
      data-testid="close-position-btn"
      disabled={!canClose}
      onClick={handleClick}
      title={
        !hasPosition
          ? CLOSE_POSITION_NO_POSITION_TITLE
          : disabled
            ? CLOSE_POSITION_ACCOUNT_ERROR_TITLE
            : spendLocked
              ? 'Orders locked — enable IBKR orders / live confirm'
              : CLOSE_POSITION_VS_CANCEL_HINT
      }
      aria-label={`Flatten position ${position.symbol}`}
    >
      {busy
        ? CLOSE_POSITION_BUTTON_BUSY_LABEL
        : hasPosition
          ? `${CLOSE_POSITION_BUTTON_LABEL} ${Math.abs(position.qty)}`
          : CLOSE_POSITION_BUTTON_LABEL}
    </button>
  );
}
