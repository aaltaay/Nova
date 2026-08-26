/** Trader command bar -- symbol, ET clock, disconnect warn. Account chrome lives on GlobalAppBar. */
import type { IbkrMode, IbkrStatus } from '../ibkr/types';
import { PaperTradingBanner } from '../ibkr/PaperTradingBanner';
import { stockViewDisconnectLabel } from '../ibkr/disconnectCopy';
import { STOCK_VIEW_TITLE } from '../constants';
import { StockViewMarketClock } from './StockViewMarketClock';
import { StockViewSymbolChip } from './StockViewSymbolChip';

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
  /** Env target (paper/live) -- used for disconnect copy when session mode is unknown. */
  gatewayMode?: 'paper' | 'live';
  connected: boolean;
  /** False while /api/ibkr/status has not been read this tab -- hide false Disconnected. */
  statusReady?: boolean;
  /** Full status when available -- drives actionable disconnect copy. */
  ibkrStatus?: Partial<IbkrStatus>;
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
  statusReady = true,
  ibkrStatus,
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

        {!connected && statusReady && (
          <span
            className="sv-header__warn"
            data-testid="sv-disconnect-warn"
            title={disconnectLabel}
          >
            {disconnectLabel}
          </span>
        )}
      </header>
    </>
  );
}
