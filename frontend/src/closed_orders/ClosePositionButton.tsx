/**
 * Flatten / close full position — ADR 007 place path (not cancel-working-order).
 * Requires the same padlock unlock (the backend arm latch) as Place an order.
 */
import { useState, type MouseEvent } from 'react';
import {
  APP_DIALOG_FLATTEN_LABEL,
  CLOSE_POSITION_ACCOUNT_ERROR_TITLE,
  CLOSE_POSITION_BUSY_WHY,
  CLOSE_POSITION_BUTTON_BUSY_LABEL,
  CLOSE_POSITION_BUTTON_LABEL,
  CLOSE_POSITION_NO_POSITION_TITLE,
  CLOSE_POSITION_PIN_LOCKED_TITLE,
  CLOSE_POSITION_VS_CANCEL_HINT,
  TICKER_TRADE_ORDER_DISCLOSURE,
  WHY_GATEWAY_NOT_CONNECTED,
} from '../constants';
import { captureBrowserAction } from '../execution_latency';
import { closeFullPosition } from '../ibkr/closeFullPosition';
import { isSpendLocked, spendLockReason } from '../ibkr/spendLock';
import { readTicketSessionUnlocked } from '../ibkr/ticketUnlock';
import type { IbkrMode, IbkrPosition } from '../ibkr/types';
import { useTradingPinGate } from '../ibkr/useTradingPinGate';
import { alertApp, confirmApp } from '../ux';
import { formatShareQty } from '../utils/formatShareQty';

interface Props {
  position: IbkrPosition;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  disabled?: boolean;
  /** Why the caller set `disabled` (ux/whyTip.ts); a failed account read when omitted. */
  why?: string | null;
  onClosed?: () => void;
  /** `menu` is the chart position overlay (same flatten path). */
  variant?: 'button' | 'menu';
  label?: string;
  testId?: string;
}

export function ClosePositionButton({
  position,
  mode,
  connected,
  spendStatus,
  disabled = false,
  why = null,
  onClosed,
  variant = 'button',
  label,
  testId = 'close-position-btn',
}: Props) {
  const [busy, setBusy] = useState(false);
  const { ensureUnlocked, pinDialog } = useTradingPinGate();
  const hasPosition = position.qty !== 0;
  const spendLocked = isSpendLocked(spendStatus);
  const canClose =
    connected && mode !== 'disconnected' && hasPosition && !spendLocked && !disabled && !busy;
  const pinLocked = !readTicketSessionUnlocked();
  // A locked Flatten says why (ux/whyTip.ts); undefined exactly when it can act.
  const lockWhy = busy
    ? CLOSE_POSITION_BUSY_WHY
    : !hasPosition
      ? CLOSE_POSITION_NO_POSITION_TITLE
      : disabled
        ? why || CLOSE_POSITION_ACCOUNT_ERROR_TITLE
        : !connected || mode === 'disconnected'
          ? WHY_GATEWAY_NOT_CONNECTED
          : spendLocked
            ? spendLockReason(spendStatus) ?? undefined
            : undefined;

  async function handleClick(e: MouseEvent) {
    e.stopPropagation();
    if (!canClose) return;
    if (!(await ensureUnlocked())) return;
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
        mode,
      });
      if (res.ok) onClosed?.();
      else await alertApp({ title: 'Flatten failed', message: res.error, tone: 'danger' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className={
          variant === 'menu' ? 'chart-position-menu__item' : 'ibkr-flatten-btn'
        }
        role={variant === 'menu' ? 'menuitem' : undefined}
        data-testid={testId}
        disabled={!canClose}
        data-why={lockWhy}
        onClick={handleClick}
        title={lockWhy ? undefined : pinLocked ? CLOSE_POSITION_PIN_LOCKED_TITLE : CLOSE_POSITION_VS_CANCEL_HINT}
        aria-label={`Flatten position ${position.symbol}`}
      >
        {busy
          ? CLOSE_POSITION_BUTTON_BUSY_LABEL
          : label
            ? label
            : hasPosition
              ? `${CLOSE_POSITION_BUTTON_LABEL} ${Math.abs(position.qty)}`
              : CLOSE_POSITION_BUTTON_LABEL}
      </button>
      {pinDialog}
    </>
  );
}
