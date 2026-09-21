/**
 * Stock Quote module — last/change + stats + Level 2 | Time & Sales.
 * Height vs Order Entry is controlled by StockViewRail's horizontal splitter.
 * Historical replay keeps this exact structure: the quote head reads the
 * replay snapshot, Level 2 shows the recorded book at the playhead when the
 * local depth recorder covered it (and says so when it did not), and Time &
 * Sales is the same view fed from reached prints
 * (architecture/historical-replay.md).
 */
import type { ReactNode } from 'react';
import { HaltEtaChip } from '../ibkr/HaltEtaChip';
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
import { StockViewQuotePrice } from './StockViewQuotePrice';
import { StockViewQuoteStats } from './StockViewQuoteStats';
import { useHistoricalSnapshot } from '../sim/useHistoricalSnapshot';
import { HistoricalTimeSales } from '../sim/HistoricalTimeSales';
import { HistoricalDepth, HistoricalL2Chip } from '../sim/HistoricalDepth';
import { historicalQuoteDetail } from '../sim/historicalQuoteDetail';

interface Props {
  selectedSymbol: string;
  detail: TickerDetail;
  listingIbkr?: IbkrListingFlags | null;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
}

function QuoteHead({ detail }: { detail: TickerDetail }) {
  return (
    <>
      <StockViewQuotePrice detail={detail} />
      <StockViewQuoteStats detail={detail} />
    </>
  );
}

function DepthAndTapeColumns({
  symbol,
  chips,
  level2,
  tape,
}: {
  symbol: string;
  /** Level 2 header chips: live halt + shortability, or the replay note. */
  chips: ReactNode;
  level2: ReactNode | null;
  tape: ReactNode | null;
}) {
  return (
    <div
      className="depth-and-tape sv-depth-and-tape"
      data-module="stock-view-depth"
      data-symbol={symbol}
      data-testid="stock-view-depth-side-by-side"
    >
      {level2 && (
        <div className="depth-and-tape__col sv-depth-and-tape__l2" data-testid="stock-view-l2-col">
          <div className="sv-md-pane">
            <div className="sv-md-pane__head">
              <h3 className="sv-md-pane__title">{STOCK_VIEW_MODULE_L2_TITLE}</h3>
              <div className="sv-md-pane__chips">{chips}</div>
            </div>
            <div className="sv-md-pane__body">{level2}</div>
          </div>
        </div>
      )}
      {tape && (
        <div className="depth-and-tape__col sv-depth-and-tape__tape" data-testid="stock-view-tape-col">
          {tape}
        </div>
      )}
    </div>
  );
}

export function StockViewDepthTape({
  selectedSymbol,
  detail,
  listingIbkr = null,
  uiActive = true,
}: Props) {
  const { ibkrConnected } = useWorkspace();
  const { isVisible } = useModuleVisibility();
  const depthSymbol = selectedSymbol.toUpperCase();
  const detailMatches = detail.symbol.toUpperCase() === depthSymbol;
  const showL2 = isVisible('level2');
  const showTape = isVisible('tape');
  const historical = useHistoricalSnapshot(depthSymbol, uiActive);

  if (historical?.active) {
    const replayDetail = historicalQuoteDetail(detail, historical);
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card"
        testId="stock-view-depth-stack"
        aria-label={STOCK_VIEW_MODULE_QUOTE_TITLE}
      >
        <QuoteHead detail={replayDetail} />
        {(showL2 || showTape) && (
          <DepthAndTapeColumns
            symbol={depthSymbol}
            // Today's halt and borrow state are not the replayed session's.
            chips={<HistoricalL2Chip depth={historical.depth} />}
            level2={showL2 ? <HistoricalDepth depth={historical.depth} /> : null}
            tape={showTape ? (
              <HistoricalTimeSales symbol={depthSymbol} snapshot={historical} uiActive={uiActive} />
            ) : null}
          />
        )}
      </StockViewModuleCard>
    );
  }

  if (!ibkrConnected || !detailMatches) {
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card sv-quote-depth-card--empty"
        testId="stock-view-depth-stack"
      >
        <QuoteHead detail={detail} />
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
        <QuoteHead detail={detail} />
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
      <QuoteHead detail={detail} />
      <DepthAndTapeColumns
        symbol={depthSymbol}
        chips={(
          <>
            <HaltEtaChip halt={detail.halt} />
            <ShortabilityChip ibkr={listingIbkr} />
          </>
        )}
        level2={showL2 ? <Level2Module symbol={depthSymbol} uiActive={uiActive} /> : null}
        tape={showTape ? <TimeSalesModule symbol={depthSymbol} embedded uiActive={uiActive} /> : null}
      />
    </StockViewModuleCard>
  );
}
