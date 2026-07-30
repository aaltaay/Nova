/**
 * Stock Quote module — one card: quote stats + Level 2 | Time & Sales.
 * Height vs Order Entry is controlled by StockViewRail's horizontal splitter.
 */
import { ShortabilityChip } from '../ibkr/ShortabilityChip';
import { Level2Module } from '../modules/Level2Module';
import { TimeSalesModule } from '../modules/TimeSalesModule';
import {
  STOCK_VIEW_MODULE_L2_TITLE,
  STOCK_VIEW_MODULE_QUOTE_TITLE,
} from '../constants';
import type { IbkrListingFlags } from '../types/ticker';
import type { TickerDetail } from '../types/ticker';
import { useModuleVisibility, useWorkspace } from '../workspace';
import { StockViewModuleCard } from './StockViewModuleCard';
import { StockViewQuoteStats } from './StockViewQuoteStats';

interface Props {
  selectedSymbol: string;
  detail: TickerDetail;
  listingIbkr?: IbkrListingFlags | null;
}

export function StockViewDepthTape({
  selectedSymbol,
  detail,
  listingIbkr = null,
}: Props) {
  const { ibkrConnected } = useWorkspace();
  const { isVisible } = useModuleVisibility();
  const depthSymbol = selectedSymbol.toUpperCase();
  const detailMatches = detail.symbol.toUpperCase() === depthSymbol;
  const showL2 = isVisible('level2');
  const showTape = isVisible('tape');

  if (!ibkrConnected || !detailMatches) {
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card sv-quote-depth-card--empty"
        testId="stock-view-depth-stack"
      >
        <StockViewQuoteStats detail={detail} />
        <p className="sv-depth-stack__hint">
          Connect IB Gateway for Level 2 and Time & Sales
        </p>
      </StockViewModuleCard>
    );
  }

  if (!showL2 && !showTape) {
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card"
        testId="stock-view-depth-stack"
      >
        <StockViewQuoteStats detail={detail} />
      </StockViewModuleCard>
    );
  }

  return (
    <StockViewModuleCard
      title={STOCK_VIEW_MODULE_QUOTE_TITLE}
      className="sv-quote-depth-card"
      testId="stock-view-depth-stack"
      aria-label={STOCK_VIEW_MODULE_QUOTE_TITLE}
    >
      <StockViewQuoteStats detail={detail} />
      <div
        className="depth-and-tape sv-depth-and-tape"
        data-module="stock-view-depth"
        data-symbol={depthSymbol}
        data-testid="stock-view-depth-side-by-side"
      >
        {showL2 && (
          <div className="depth-and-tape__col sv-depth-and-tape__l2" data-testid="stock-view-l2-col">
            <div className="sv-md-pane">
              <div className="sv-md-pane__head">
                <h3 className="sv-md-pane__title">{STOCK_VIEW_MODULE_L2_TITLE}</h3>
                <ShortabilityChip ibkr={listingIbkr} />
              </div>
              <div className="sv-md-pane__body">
                <Level2Module symbol={depthSymbol} />
              </div>
            </div>
          </div>
        )}
        {showTape && (
          <div className="depth-and-tape__col sv-depth-and-tape__tape" data-testid="stock-view-tape-col">
            <TimeSalesModule symbol={depthSymbol} embedded />
          </div>
        )}
      </div>
    </StockViewModuleCard>
  );
}
