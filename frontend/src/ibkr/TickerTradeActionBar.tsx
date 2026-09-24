/** Trading action bar — Open / Close.
 * Reuses the IBKR order API; does not invent a second order path. */
import { useState } from 'react';
import {
  APP_DIALOG_FLATTEN_LABEL,
  CLOSE_POSITION_ACCOUNT_ERROR_TITLE,
  CLOSE_POSITION_BUSY_WHY,
  CLOSE_POSITION_DISARMED_TITLE,
  CLOSE_POSITION_NO_POSITION_TITLE,
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
import { flattenSpendLockReason, isDisarmed, spendLockReason } from './spendLock';
import type { PlaceOrderResult } from './placeOrder';
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
  // `seq` lets the ticket's Last line show each new Flatten outcome: the rail
  // hides this bar's own footer, so a result or refusal written only there
  // was never seen (QA R32).
  const [resultMsg, setResultMsgState] = useState<{ ok: boolean; text: string; seq: number } | null>(null);
  const setResultMsg = (next: { ok: boolean; text: string } | null) =>
    setResultMsgState((prev) => (next ? { ...next, seq: (prev?.seq ?? 0) + 1 } : null));

  const gatewayReason = !connected
    ? 'IBKR disconnected — connect Gateway (Trading tab) to place orders'
    : mode === 'disconnected'
      ? 'IBKR mode offline'
      : null;
  const disabledReason = gatewayReason ?? spendLockReason(spendStatus);
  // Disarmed is no lock for Flatten: only the locks the backend holds a flatten to.
  const flattenLockReason = gatewayReason ?? flattenSpendLockReason(spendStatus);

  const canFlatten = flattenLockReason == null && !closing && !accountError;
  const modeLabel =
    mode === 'paper' ? 'PAPER' : mode === 'live' ? '⚠ LIVE' : mode === 'sim' ? 'SIM' : 'OFFLINE';
  const hasPosition = position != null && position.qty !== 0;
  // A locked Flatten says why (ux/whyTip.ts); null exactly when it can act.
  const flattenWhy = !hasPosition
    ? CLOSE_POSITION_NO_POSITION_TITLE
    : closing
      ? CLOSE_POSITION_BUSY_WHY
      : accountError
        ? CLOSE_POSITION_ACCOUNT_ERROR_TITLE
        : flattenLockReason;
  const compactChrome = variant === 'rail';
  const showAccount = !compactChrome;

  async function handleClose() {
    if (!canFlatten || !position || position.qty === 0) return;
    // No padlock step: arming here would also unlock every order that opens.
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
      const data = await closeFullPosition(symbol, position.qty, {
        referencePrice: position.market_price,
        mode,
      });
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
            externalResult={resultMsg}
          />
        </div>

        <div className="ticker-trade-bar-close">
          {!compactChrome && <span className="ticker-trade-bar-group-label">Close</span>}
          <button
            type="button"
            className="ticker-trade-close-btn"
            disabled={!canFlatten || !hasPosition}
            data-why={flattenWhy ?? undefined}
            onClick={() => void handleClose()}
            title={
              flattenWhy
                ? undefined
                : isDisarmed(spendStatus)
                  ? CLOSE_POSITION_DISARMED_TITLE
                  : 'Flatten position with market order'
            }
          >
            {closing
              ? 'Closing…'
              : hasPosition
                ? `Flatten ${Math.abs(position!.qty)}`
                : 'No position'}
          </button>
        </div>
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
    </div>
  );
}
