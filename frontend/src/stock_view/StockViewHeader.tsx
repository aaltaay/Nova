/** Stock View command bar — symbol, account metrics, Paper/Live, mode, lock. */
import type { IbkrAccountSummary, IbkrMode } from '../ibkr/types';
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
  connected: boolean;
  summary: IbkrAccountSummary | null;
  onLookup: (symbol: string) => void;
}

function fmtDollar(n: number | null | undefined) {
  if (n == null) return '—';
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
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
  connected,
  summary,
  onLookup,
}: Props) {
  return (
    <header className="sv-header" data-testid="stock-view-header">
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

      <div className="sv-header__spacer" aria-hidden />

      <div className="sv-header__account" aria-label="Account">
        <StockViewAccountModeCapsule mode={mode} />
        {!connected && <span className="sv-header__warn">Disconnected</span>}
        {summary?.connected && (
          <>
            <span className="sv-header__metric">
              <label>Net Liq</label> {fmtDollar(summary.NetLiquidation)}
            </span>
            <span className="sv-header__metric">
              <label>BP</label> {fmtDollar(summary.BuyingPower)}
            </span>
          </>
        )}
      </div>

      <StockViewOperatorModeCapsule />
    </header>
  );
}
