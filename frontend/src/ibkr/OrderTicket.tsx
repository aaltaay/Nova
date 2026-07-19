import { useEffect, useState } from 'react';
import { ManualOrderTicket } from './ManualOrderTicket';
import type { PlaceOrderResult } from './placeOrder';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

interface Props {
  defaultSymbol?: string;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  onOrderPlaced?: (result: PlaceOrderResult) => void;
}

export function OrderTicket({
  defaultSymbol = '',
  mode,
  connected,
  spendStatus,
  summary,
  positions,
  onOrderPlaced,
}: Props) {
  const [symbol, setSymbol] = useState(defaultSymbol);

  const modeLabel = mode === 'paper' ? 'PAPER' : mode === 'live' ? '⚠ LIVE' : 'DISCONNECTED';
  const position =
    positions.find(item => item.symbol.toUpperCase() === symbol.toUpperCase()) ?? null;
  const referencePrice = position?.market_price ?? null;

  useEffect(() => {
    setSymbol(defaultSymbol);
  }, [defaultSymbol]);

  return (
    <div className="ibkr-order-ticket">
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
          disabled={!connected}
          className="ibkr-input"
        />
      </div>

      <ManualOrderTicket
        symbol={symbol}
        mode={mode}
        connected={connected}
        spendStatus={spendStatus}
        summary={summary}
        position={position}
        referencePrice={referencePrice}
        onOrderPlaced={onOrderPlaced}
      />

      <button
        type="button"
        className="ibkr-automate-btn"
        disabled
        title="Coming soon — strategy/pattern-based automated execution"
      >
        ⚡ Automate (coming soon)
      </button>
    </div>
  );
}
