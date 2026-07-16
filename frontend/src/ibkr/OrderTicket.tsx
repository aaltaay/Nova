import React, { useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { IbkrMode } from './types';

interface Props {
  defaultSymbol?: string;
  mode: IbkrMode;
  onOrderPlaced?: (result: { ok: boolean; order_id: number | null; error: string | null }) => void;
}

export function OrderTicket({ defaultSymbol = '', mode, onOrderPlaced }: Props) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [qty, setQty] = useState('');
  const [orderType, setOrderType] = useState<'MKT' | 'LMT'>('MKT');
  const [limitPrice, setLimitPrice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<{ ok: boolean; message: string } | null>(null);

  const modeLabel = mode === 'paper' ? 'PAPER' : mode === 'live' ? '⚠ LIVE' : 'DISCONNECTED';

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol || !qty || submitting) return;
    setSubmitting(true);
    setLastResult(null);

    try {
      const body: Record<string, unknown> = {
        symbol: symbol.toUpperCase(),
        side,
        qty: parseFloat(qty),
        order_type: orderType,
      };
      if (orderType === 'LMT' && limitPrice) {
        body.limit_price = parseFloat(limitPrice);
      }

      const res = await fetch(`${API_BASE_URL}/api/ibkr/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await res.json();
      const msg = data.ok
        ? `Order placed (#${data.order_id}) — ${data.mode} account`
        : `Error: ${data.error}`;
      setLastResult({ ok: data.ok, message: msg });
      onOrderPlaced?.(data);
    } catch {
      setLastResult({ ok: false, message: 'Network error' });
    } finally {
      setSubmitting(false);
    }
  }

  const disabled = mode === 'disconnected' || submitting;

  return (
    <form className="ibkr-order-ticket" onSubmit={submit}>
      <div className="ibkr-order-header">
        <span className="ibkr-order-title">Order Ticket</span>
        <span className={`ibkr-mode-badge ibkr-mode-${mode}`}>{modeLabel}</span>
      </div>

      <div className="ibkr-order-row">
        <label>Symbol</label>
        <input
          type="text"
          value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase())}
          placeholder="AAPL"
          maxLength={10}
          disabled={disabled}
          className="ibkr-input"
        />
      </div>

      <div className="ibkr-order-row ibkr-side-row">
        <button
          type="button"
          className={`ibkr-side-btn${side === 'BUY' ? ' active-buy' : ''}`}
          onClick={() => setSide('BUY')}
          disabled={disabled}
        >
          BUY
        </button>
        <button
          type="button"
          className={`ibkr-side-btn${side === 'SELL' ? ' active-sell' : ''}`}
          onClick={() => setSide('SELL')}
          disabled={disabled}
        >
          SELL
        </button>
      </div>

      <div className="ibkr-order-row">
        <label>Qty</label>
        <input
          type="number"
          value={qty}
          onChange={e => setQty(e.target.value)}
          placeholder="100"
          min="1"
          step="1"
          disabled={disabled}
          className="ibkr-input"
        />
      </div>

      <div className="ibkr-order-row ibkr-side-row">
        <button
          type="button"
          className={`ibkr-side-btn${orderType === 'MKT' ? ' active-type' : ''}`}
          onClick={() => setOrderType('MKT')}
          disabled={disabled}
        >
          Market Order
        </button>
        <button
          type="button"
          className={`ibkr-side-btn${orderType === 'LMT' ? ' active-type' : ''}`}
          onClick={() => setOrderType('LMT')}
          disabled={disabled}
        >
          Limit Order
        </button>
      </div>

      {orderType === 'LMT' && (
        <div className="ibkr-order-row">
          <label>Limit $</label>
          <input
            type="number"
            value={limitPrice}
            onChange={e => setLimitPrice(e.target.value)}
            placeholder="0.00"
            min="0"
            step="0.01"
            disabled={disabled}
            className="ibkr-input"
          />
        </div>
      )}

      <button
        type="submit"
        className={`ibkr-submit-btn ibkr-submit-${side.toLowerCase()}`}
        disabled={disabled}
      >
        {submitting ? 'Placing…' : `${side} ${symbol || '—'}`}
      </button>

      {lastResult && (
        <div className={`ibkr-order-result ${lastResult.ok ? 'ok' : 'err'}`}>
          {lastResult.message}
        </div>
      )}

      <button
        type="button"
        className="ibkr-automate-btn"
        disabled
        title="Coming soon — strategy/pattern-based automated execution"
      >
        ⚡ Automate (coming soon)
      </button>
    </form>
  );
}
