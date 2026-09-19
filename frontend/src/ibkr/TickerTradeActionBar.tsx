/** Trading action bar — Open / Close / Automate.
 * Reuses IBKR order API + useExecutor; does not invent a second order path. */
import { useState } from 'react';
import {
  APP_DIALOG_FLATTEN_LABEL,
  CLOSE_POSITION_ACCOUNT_ERROR_TITLE,
  CLOSE_POSITION_PIN_LOCKED_TITLE,
  STOCK_VIEW_MODULE_OPEN_TITLE,
  TICKER_TRADE_ORDER_DISCLOSURE,
} from '../constants';
import { NovaActionRuntimeSync } from '../hotkeys/NovaActionRuntimeSync';
import { TradingQuickBar } from '../hotkeys/TradingQuickBar';
import { confirmApp } from '../ux';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { closeFullPosition } from './closeFullPosition';
import { executionTransportError } from './executionTransportError';
import { ManualOrderTicket } from './ManualOrderTicket';
import { notifyOrderRejected } from './notifyOrderRejected';
import { spendLockReason } from './spendLock';
import type { PlaceOrderResult } from './placeOrder';
import { readTicketSessionUnlocked } from './ticketUnlock';
import { TickerTradeAutomateControls } from './TickerTradeAutomateControls';
import { useTradingPinGate } from './useTradingPinGate';
import type { IbkrListingFlags } from '../types/ticker';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

interface Props {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  /** Set when useIbkrAccount last poll failed — disable Flatten (last-good qty). */
  accountError?: string | null;
  position: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  referencePrice: number | null;
  listingIbkr?: IbkrListingFlags | null;
  onOrderPlaced?: (result?: PlaceOrderResult) => void;
  /**
   * `footer` — full chrome (account + automate).
   * `sidebar` — stacked under Level 2 (legacy Stock View).
   * `rail` — Stock View terminal rail under L2+T&S: ticket + flatten only
   *   (account/automate in header; height vs depth via rail horizontal splitter).
   */
  variant?: 'footer' | 'sidebar' | 'rail';
}

export function TickerTradeActionBar({
  symbol,
  mode,
  connected,
  spendStatus,
  accountError = null,
  position,
  summary,
  referencePrice,
  listingIbkr = null,
  onOrderPlaced,
  variant = 'footer',
}: Props) {
  const [closing, setClosing] = useState(false);
  const [resultMsg, setResultMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const { ensureUnlocked, pinDialog } = useTradingPinGate();

  const disabledReason = !connected
    ? 'IBKR disconnected — connect Gateway (Trading tab) to place orders'
    : mode === 'disconnected'
      ? 'IBKR mode offline'
      : spendLockReason(spendStatus);

  const canTrade = connected && mode !== 'disconnected' && disabledReason == null && !closing;
  const canFlatten = canTrade && !accountError;
  const modeLabel =
    mode === 'paper' ? 'PAPER' : mode === 'live' ? '⚠ LIVE' : mode === 'sim' ? 'SIM' : 'OFFLINE';
  const hasPosition = position != null && position.qty !== 0;
  const compactChrome = variant === 'rail';
  const showAccount = !compactChrome;
  const showAutomate = !compactChrome;

  async function handleClose() {
    if (!canFlatten || !position || position.qty === 0) return;
    if (!(await ensureUnlocked())) return;
    const absQty = formatShareQty(Math.abs(position.qty));
    const closeSide: 'BUY' | 'SELL' = position.qty > 0 ? 'SELL' : 'BUY';
    const confirmed = await confirmApp({
      title: `Flatten ${symbol}?`,
      message:
        `${TICKER_TRADE_ORDER_DISCLOSURE}\n\n` +
        `Flatten (close full position) ${absQty} shares of ${symbol} with a ${closeSide} market order ` +
        `on the ${mode.toUpperCase()} account?\n\n` +
        `This is not Cancel — Cancel only removes a working order.`,
      confirmLabel: APP_DIALOG_FLATTEN_LABEL,
      tone: 'danger',
    });
    if (!confirmed) return;

    setClosing(true);
    setResultMsg(null);
    try {
      const data = await closeFullPosition(symbol, position.qty);
      if (data.ok) {
        setResultMsg({
          ok: true,
          text: `Flatten order #${data.order_id} (${data.mode ?? mode})`,
        });
        onOrderPlaced?.({
          ok: true,
          order_id: data.order_id,
          error: null,
          mode: data.mode,
        });
      } else {
        setResultMsg({ ok: false, text: data.error });
        void notifyOrderRejected({
          message: data.error,
          reasonCode: data.place?.reason_code,
          order: {
            symbol,
            side: closeSide,
            qty: Math.abs(position.qty),
            mode,
          },
        });
      }
    } catch (error) {
      const text = executionTransportError(error);
      setResultMsg({ ok: false, text });
      void notifyOrderRejected({ message: text });
    } finally {
      setClosing(false);
    }
  }

  const barClass =
    variant === 'rail'
      ? 'ticker-trade-bar ticker-trade-bar--rail'
      : variant === 'sidebar'
        ? 'ticker-trade-bar ticker-trade-bar--sidebar'
        : 'ticker-trade-bar';

  return (
    <div className={barClass} role="region" aria-label="Trading actions">
      <NovaActionRuntimeSync
        symbol={symbol}
        position={position}
        accountError={accountError}
      />
      <TradingQuickBar />
      <div className="ticker-trade-bar-top">
        {showAccount && (
          <div className="ticker-trade-bar-account">
            <span className={`ibkr-mode-badge ibkr-mode-${mode}`}>{modeLabel}</span>
            {summary?.connected && (
              <>
                <span className="ticker-trade-bar-metric">
                  <label>Net Liq</label> {formatMoney(summary.NetLiquidation, 0)}
                </span>
                <span className="ticker-trade-bar-metric">
                  <label>BP</label> {formatMoney(summary.BuyingPower, 0)}
                </span>
              </>
            )}
            {hasPosition && (
              <span className="ticker-trade-bar-metric">
                <label>Pos</label> {formatShareQty(position!.qty)} @{' '}
                {position!.avg_cost?.toFixed(2) ?? '—'}
              </span>
            )}
          </div>
        )}

        {compactChrome && hasPosition && (
          <div className="ticker-trade-bar-account ticker-trade-bar-account--pos-only">
            <span className="ticker-trade-bar-metric">
              <label>Pos</label> {formatShareQty(position!.qty)} @{' '}
              {position!.avg_cost?.toFixed(2) ?? '—'}
            </span>
          </div>
        )}

        <div className="ticker-trade-bar-open">
          {!compactChrome && (
            <span className="ticker-trade-bar-group-label">{STOCK_VIEW_MODULE_OPEN_TITLE}</span>
          )}
          <ManualOrderTicket
            symbol={symbol}
            mode={mode}
            connected={connected}
            spendStatus={spendStatus}
            summary={summary}
            position={position}
            referencePrice={referencePrice}
            listingIbkr={listingIbkr}
            onOrderPlaced={(result) => onOrderPlaced?.(result)}
          />
        </div>

        <div className="ticker-trade-bar-close">
          {!compactChrome && <span className="ticker-trade-bar-group-label">Close</span>}
          <button
            type="button"
            className="ticker-trade-close-btn"
            disabled={!canFlatten || !hasPosition}
            onClick={() => void handleClose()}
            title={
              !hasPosition
                ? 'No open position in this symbol'
                : accountError
                  ? CLOSE_POSITION_ACCOUNT_ERROR_TITLE
                  : !readTicketSessionUnlocked()
                    ? CLOSE_POSITION_PIN_LOCKED_TITLE
                    : disabledReason ?? 'Flatten position with market order'
            }
          >
            {closing
              ? 'Closing…'
              : hasPosition
                ? `Flatten ${Math.abs(position!.qty)}`
                : 'No position'}
          </button>
        </div>

        {showAutomate && <TickerTradeAutomateControls enabled />}
      </div>

      <div className="ticker-trade-bar-footer">
        <span className="ticker-trade-bar-disclosure">{TICKER_TRADE_ORDER_DISCLOSURE}</span>
        {disabledReason && <span className="ticker-trade-bar-disabled-why">{disabledReason}</span>}
        {resultMsg && (
          <span className={`ticker-trade-bar-result ${resultMsg.ok ? 'ok' : 'err'}`}>
            {resultMsg.text}
          </span>
        )}
      </div>
      {pinDialog}
    </div>
  );
}
