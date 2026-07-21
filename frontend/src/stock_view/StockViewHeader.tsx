/** Trader window command bar — symbol, ET clock, account metrics, Paper/Live, mode. */
import type { IbkrAccountSummary, IbkrMode, IbkrStatus } from '../ibkr/types';
import { PaperTradingBanner } from '../ibkr/PaperTradingBanner';
import { stockViewDisconnectLabel } from '../ibkr/disconnectCopy';
import { STOCK_VIEW_TITLE } from '../constants';
import { formatMoney } from '../utils/formatMoney';
import { StockViewMarketClock } from './StockViewMarketClock';
import { StockViewSymbolChip } from './StockViewSymbolChip';
import {
  StockViewAccountModeCapsule,
  StockViewOperatorModeCapsule,
} from './StockViewTradingChrome';

interface Props {
  symbol: string;
  detailReady: boolean;
  detailSymbol?: string;
  mainPrice: number | null;
  mainChangeAbs: number | null;
  mainChangePct: number | null;
  isPositive: boolean;
  refreshing: boolean;
  mode: IbkrMode;
  /** Env target (paper/live) — capsule selection when disconnected. */
  gatewayMode?: 'paper' | 'live';
  connected: boolean;
  /** Full status when available — drives actionable disconnect copy. */
  ibkrStatus?: Partial<IbkrStatus>;
  summary: IbkrAccountSummary | null;
  onLookup: (symbol: string) => void;
}

export function StockViewHeader({
  symbol,
  detailReady,
  detailSymbol,
  mainPrice,
  mainChangeAbs,
  mainChangePct,
  isPositive,
  refreshing,
  mode,
  gatewayMode,
  connected,
  ibkrStatus,
  summary,
  onLookup,
}: Props) {
  const disconnectLabel = stockViewDisconnectLabel({
    disconnect_hint: ibkrStatus?.disconnect_hint,
    gateway_mode: gatewayMode ?? ibkrStatus?.gateway_mode,
  });

  return (
    <>
      <PaperTradingBanner mode={mode} />
      <header className="sv-header" data-testid="stock-view-header">
        <div className="sv-header__brand">
          <span className="sv-header__nova">Nova</span>
          <span className="sv-header__title">{STOCK_VIEW_TITLE}</span>
        </div>
        <StockViewSymbolChip
          symbol={symbol}
          displaySymbol={detailReady ? (detailSymbol ?? symbol) : symbol}
          mainPrice={detailReady ? mainPrice : null}
          mainChangeAbs={detailReady ? mainChangeAbs : null}
          mainChangePct={detailReady ? mainChangePct : null}
          isPositive={isPositive}
          refreshing={detailReady && refreshing}
          onCommit={onLookup}
        />

        <StockViewMarketClock />

        <div className="sv-header__spacer" aria-hidden />

        <div className="sv-header__account" aria-label="Account">
          <StockViewAccountModeCapsule
            mode={mode}
            gatewayMode={gatewayMode}
            disconnectHint={ibkrStatus?.disconnect_hint}
          />
          {!connected && (
            <span
              className="sv-header__warn"
              data-testid="sv-disconnect-warn"
              title={disconnectLabel}
            >
              {disconnectLabel}
            </span>
          )}
          {summary?.connected && (
            <>
              <span className="sv-header__metric">
                <label>Net Liq</label> {formatMoney(summary.NetLiquidation, 0)}
              </span>
              <span className="sv-header__metric">
                <label>BP</label> {formatMoney(summary.BuyingPower, 0)}
              </span>
            </>
          )}
        </div>

        <StockViewOperatorModeCapsule />
      </header>
    </>
  );
}
