/** Trading action bar — Open / Close / Automate.
 * Reuses IBKR order API + useExecutor; does not invent a second order path. */
import { useState } from 'react';
import {
  STOCK_VIEW_MODULE_OPEN_TITLE,
  TICKER_TRADE_ORDER_DISCLOSURE,
} from '../constants';
import { NovaActionRuntimeSync } from '../hotkeys/NovaActionRuntimeSync';
import { TradingQuickBar } from '../hotkeys/TradingQuickBar';
import { ManualOrderTicket } from './ManualOrderTicket';
import { placeIbkrOrder } from './placeOrder';
import { TickerTradeAutomateControls } from './TickerTradeAutomateControls';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

interface Props {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  position: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  referencePrice: number | null;
  onOrderPlaced?: () => void;
  /**
   * `footer` — full chrome (account + automate).
   * `sidebar` — stacked under Level 2 (legacy Stock View).
   * `rail` — Stock View terminal rail under L2+T&S: ticket + flatten only
   *   (account/automate in header; height vs depth via rail horizontal splitter).
   */
  variant?: 'footer' | 'sidebar' | 'rail';
}

function fmtDollar(n: number | null | undefined) {
  if (n == null) return '—';
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function TickerTradeActionBar({
  symbol,
  mode,
  connected,
  spendStatus,
  position,
  summary,
  referencePrice,
  onOrderPlaced,
  variant = 'footer',
}: Props) {
  const [closing, setClosing] = useState(false);
  const [resultMsg, setResultMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const disabledReason = !connected
    ? 'IBKR disconnected — connect Gateway (Trading tab) to place orders'
    : mode === 'disconnected'
      ? 'IBKR mode offline'
      : spendStatus === 'locked'
        ? 'Orders locked — enable IBKR orders in Nova settings/environment'
        : spendStatus === 'locked_live_unconfirmed'
          ? 'Live orders locked — explicit live confirmation is required'
          : null;

  const canTrade = connected && mode !== 'disconnected' && disabledReason == null && !closing;
  const modeLabel = mode === 'paper' ? 'PAPER' : mode === 'live' ? '⚠ LIVE' : 'OFFLINE';
  const hasPosition = position != null && position.qty !== 0;
  const compactChrome = variant === 'rail';
  const showAccount = !compactChrome;
  const showAutomate = !compactChrome;

  async function handleClose() {
    if (!canTrade || !position || position.qty === 0) return;
    const absQty = Math.abs(position.qty);
    const closeSide: 'BUY' | 'SELL' = position.qty > 0 ? 'SELL' : 'BUY';
    const confirmed = window.confirm(
      `${TICKER_TRADE_ORDER_DISCLOSURE}\n\n` +
        `Close (flatten) ${absQty} shares of ${symbol} with a ${closeSide} market order ` +
        `on the ${mode.toUpperCase()} account?`,
    );
    if (!confirmed) return;

    setClosing(true);
    setResultMsg(null);
    try {
      const data = await placeIbkrOrder({
        symbol: symbol.toUpperCase(),
        side: closeSide,
        qty: absQty,
        order_type: 'MKT',
        outside_rth: false,
      });
      setResultMsg({
        ok: data.ok,
        text: data.ok
          ? `Close order #${data.order_id} (${data.mode ?? mode})`
          : data.error ?? 'Close failed',
      });
      if (data.ok) onOrderPlaced?.();
    } catch {
      setResultMsg({ ok: false, text: 'Network error' });
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
      <NovaActionRuntimeSync symbol={symbol} position={position} />
      <TradingQuickBar />
      <div className="ticker-trade-bar-top">
        {showAccount && (
          <div className="ticker-trade-bar-account">
            <span className={`ibkr-mode-badge ibkr-mode-${mode}`}>{modeLabel}</span>
            {summary?.connected && (
              <>
                <span className="ticker-trade-bar-metric">
                  <label>Net Liq</label> {fmtDollar(summary.NetLiquidation)}
                </span>
                <span className="ticker-trade-bar-metric">
                  <label>BP</label> {fmtDollar(summary.BuyingPower)}
                </span>
              </>
            )}
            {hasPosition && (
              <span className="ticker-trade-bar-metric">
                <label>Pos</label> {position!.qty} @ {position!.avg_cost?.toFixed(2) ?? '—'}
              </span>
            )}
          </div>
        )}

        {compactChrome && hasPosition && (
          <div className="ticker-trade-bar-account ticker-trade-bar-account--pos-only">
            <span className="ticker-trade-bar-metric">
              <label>Pos</label> {position!.qty} @ {position!.avg_cost?.toFixed(2) ?? '—'}
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
            onOrderPlaced={() => onOrderPlaced?.()}
          />
        </div>

        <div className="ticker-trade-bar-close">
          {!compactChrome && <span className="ticker-trade-bar-group-label">Close</span>}
          <button
            type="button"
            className="ticker-trade-close-btn"
            disabled={!canTrade || !hasPosition}
            onClick={handleClose}
            title={
              !hasPosition
                ? 'No open position in this symbol'
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
    </div>
  );
}
