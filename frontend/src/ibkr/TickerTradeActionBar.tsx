/** Bottom action bar for the full ticker trading page — Open / Close / Automate.
 * Reuses IBKR order API + useExecutor; does not invent a second order path. */
import { useCallback, useEffect, useState } from 'react';
import {
  API_BASE_URL,
  TICKER_TRADE_DEFAULT_QTY,
  TICKER_TRADE_ORDER_DISCLOSURE,
} from '../constants';
import { TickerTradeAutomateControls } from './TickerTradeAutomateControls';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

interface Props {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  position: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  onOrderPlaced?: () => void;
}

function fmtDollar(n: number | null | undefined) {
  if (n == null) return '—';
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

async function placeIbkrOrder(
  symbol: string,
  side: 'BUY' | 'SELL',
  qty: number,
  orderType: 'MKT' | 'LMT',
  limitPrice?: number,
) {
  const body: Record<string, unknown> = {
    symbol: symbol.toUpperCase(),
    side,
    qty,
    order_type: orderType,
  };
  if (orderType === 'LMT' && limitPrice != null) body.limit_price = limitPrice;

  const res = await fetch(`${API_BASE_URL}/api/ibkr/order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json() as Promise<{
    ok: boolean;
    order_id: number | null;
    error: string | null;
    mode?: string;
  }>;
}

export function TickerTradeActionBar({
  symbol,
  mode,
  connected,
  position,
  summary,
  onOrderPlaced,
}: Props) {
  const [qty, setQty] = useState(String(TICKER_TRADE_DEFAULT_QTY));
  const [orderType, setOrderType] = useState<'MKT' | 'LMT'>('MKT');
  const [limitPrice, setLimitPrice] = useState('');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [submitting, setSubmitting] = useState(false);
  const [closing, setClosing] = useState(false);
  const [resultMsg, setResultMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    setResultMsg(null);
    setQty(String(TICKER_TRADE_DEFAULT_QTY));
  }, [symbol]);

  const disabledReason = !connected
    ? 'IBKR disconnected — connect Gateway (Trading tab) to place orders'
    : mode === 'disconnected'
      ? 'IBKR mode offline'
      : null;

  const canTrade = connected && mode !== 'disconnected' && !submitting && !closing;
  const modeLabel = mode === 'paper' ? 'PAPER' : mode === 'live' ? '⚠ LIVE' : 'OFFLINE';
  const hasPosition = position != null && position.qty !== 0;

  const handleOpen = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!canTrade) return;
      const q = parseFloat(qty);
      if (!q || q <= 0) {
        setResultMsg({ ok: false, text: 'Enter a valid quantity' });
        return;
      }
      if (orderType === 'LMT' && !limitPrice) {
        setResultMsg({ ok: false, text: 'Limit price required' });
        return;
      }

      const confirmed = window.confirm(
        `${TICKER_TRADE_ORDER_DISCLOSURE}\n\n` +
          `Place ${side} ${q} ${symbol} (${orderType}${orderType === 'LMT' ? ` @ $${limitPrice}` : ''}) ` +
          `on the ${mode.toUpperCase()} account?`,
      );
      if (!confirmed) return;

      setSubmitting(true);
      setResultMsg(null);
      try {
        const data = await placeIbkrOrder(
          symbol,
          side,
          q,
          orderType,
          orderType === 'LMT' ? parseFloat(limitPrice) : undefined,
        );
        setResultMsg({
          ok: data.ok,
          text: data.ok
            ? `Opened #${data.order_id} (${data.mode ?? mode})`
            : data.error ?? 'Order failed',
        });
        if (data.ok) onOrderPlaced?.();
      } catch {
        setResultMsg({ ok: false, text: 'Network error' });
      } finally {
        setSubmitting(false);
      }
    },
    [canTrade, qty, orderType, limitPrice, side, symbol, mode, onOrderPlaced],
  );

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
      const data = await placeIbkrOrder(symbol, closeSide, absQty, 'MKT');
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

  return (
    <div className="ticker-trade-bar" role="region" aria-label="Trading actions">
      <div className="ticker-trade-bar-top">
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

        <form className="ticker-trade-bar-open" onSubmit={handleOpen}>
          <span className="ticker-trade-bar-group-label">Open</span>
          <div className="ticker-trade-bar-sides">
            <button
              type="button"
              className={`ibkr-side-btn${side === 'BUY' ? ' active-buy' : ''}`}
              onClick={() => setSide('BUY')}
              disabled={!canTrade}
            >
              BUY
            </button>
            <button
              type="button"
              className={`ibkr-side-btn${side === 'SELL' ? ' active-sell' : ''}`}
              onClick={() => setSide('SELL')}
              disabled={!canTrade}
            >
              SELL
            </button>
          </div>
          <input
            className="ibkr-input ticker-trade-bar-qty"
            type="number"
            min="1"
            step="1"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            disabled={!canTrade}
            aria-label="Quantity"
            placeholder="Qty"
          />
          <div className="ticker-trade-bar-sides">
            <button
              type="button"
              className={`ibkr-side-btn${orderType === 'MKT' ? ' active-type' : ''}`}
              onClick={() => setOrderType('MKT')}
              disabled={!canTrade}
            >
              MKT
            </button>
            <button
              type="button"
              className={`ibkr-side-btn${orderType === 'LMT' ? ' active-type' : ''}`}
              onClick={() => setOrderType('LMT')}
              disabled={!canTrade}
            >
              LMT
            </button>
          </div>
          {orderType === 'LMT' && (
            <input
              className="ibkr-input ticker-trade-bar-limit"
              type="number"
              min="0"
              step="0.01"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              disabled={!canTrade}
              aria-label="Limit price"
              placeholder="Limit $"
            />
          )}
          <button
            type="submit"
            className={`ibkr-submit-btn ibkr-submit-${side.toLowerCase()} ticker-trade-bar-submit`}
            disabled={!canTrade}
            title={disabledReason ?? `Place ${side} order via IBKR`}
          >
            {submitting ? 'Placing…' : `Open ${side}`}
          </button>
        </form>

        <div className="ticker-trade-bar-close">
          <span className="ticker-trade-bar-group-label">Close</span>
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

        <TickerTradeAutomateControls enabled />
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
