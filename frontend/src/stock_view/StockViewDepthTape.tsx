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
import { captureQuoteDetail, historicalQuoteDetail, simEmptyQuoteDetail } from '../sim/historicalQuoteDetail';
import { simRailNote } from '../sim/simReplayTarget';
import { SimReplayTargetNotice } from '../sim/SimReplayTargetNotice';
import { useSimReplayTarget } from '../sim/useSimReplayTarget';
import { CaptureReplayL2Chip } from '../sim/CaptureReplayChip';
import {
  SIM_CAPTURE_TAPE_NOT_RECORDED,
  SIM_CAPTURE_TAPE_TITLE,
  SIM_REPLAY_TAPE_STATUS,
} from '../sim/simConstants';
import { StockViewVenueTag } from './StockViewVenueTag';

interface Props {
  selectedSymbol: string;
  detail: TickerDetail;
  listingIbkr?: IbkrListingFlags | null;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
}

function QuoteHead({ detail, symbol }: { detail: TickerDetail; symbol: string }) {
  return (
    <>
      <div className="sv-quote-head">
        <StockViewQuotePrice detail={detail} />
        {/* Practice venue as a card tag, not a page banner. */}
        <StockViewVenueTag symbol={symbol} />
      </div>
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
  const { sim, clock } = useSimReplayTarget(depthSymbol);
  // At the live edge a Sim tab is live whatever is loaded (ADR 020 live-edge
  // amendment): the historical panes wait for the scrub back, and the live
  // modules remount across the edge so they (re)open the real line rather
  // than sit on the replay slot they held off it.
  const liveEdge = sim && clock?.live_edge === true;
  const feedKey = sim ? (liveEdge ? 'live-edge' : 'replay') : 'live';

  if (historical?.active && !liveEdge) {
    const replayDetail = historicalQuoteDetail(detail, historical);
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card"
        testId="stock-view-depth-stack"
        aria-label={STOCK_VIEW_MODULE_QUOTE_TITLE}
      >
        <QuoteHead detail={replayDetail} symbol={depthSymbol} />
        {(showL2 || showTape) && (
          <DepthAndTapeColumns
            symbol={depthSymbol}
            // Today's halt and borrow state are not the replayed session's.
            chips={<HistoricalL2Chip depth={historical.depth} />}
            // Holds the replay depth slot a bot needs while shown (QA R44).
            level2={showL2 ? <HistoricalDepth depth={historical.depth} holdLineFor={depthSymbol} /> : null}
            tape={showTape ? (
              <HistoricalTimeSales symbol={depthSymbol} snapshot={historical} uiActive={uiActive} />
            ) : null}
          />
        )}
      </StockViewModuleCard>
    );
  }

  // Sim with nothing for this ticker: say so, inside the card, with the one
  // action that fixes it (SimReplayTargetNotice) -- never a band over the page.
  // Falling through would render the live panes, badged LIVE, with today's
  // halt and borrow chips, over a replay.
  const simNote = simRailNote(depthSymbol, clock, sim);
  if (simNote) {
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card sv-quote-depth-card--empty"
        testId="stock-view-depth-stack"
      >
        <QuoteHead detail={simEmptyQuoteDetail(detail, depthSymbol)} symbol={depthSymbol} />
        <p className="sv-depth-stack__hint" data-testid="stock-view-sim-rail-note">{simNote}</p>
        <SimReplayTargetNotice symbol={depthSymbol} />
      </StockViewModuleCard>
    );
  }

  // A Session Record replaying for this tab, off the edge: the panes are the
  // recording's, so they say REPLAY, show the recording's L2 state instead of
  // today's halt / borrow chips, and state a gap as a gap (QA 2026-09-22, R16 / R11).
  // Its quote stats are the recording's too -- never today's live Vol / High /
  // Low / Gap% (QA W8).
  const captureReplay = sim && !liveEdge && clock?.replay_source === 'capture'
    && (clock.replay_symbol ?? '').toUpperCase() === depthSymbol;
  const gap = captureReplay && clock?.replay_quote?.covered === false;
  const quoteDetail = captureReplay && clock ? captureQuoteDetail(detail, clock, depthSymbol) : detail;

  if (!ibkrConnected || !detailMatches) {
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_QUOTE_TITLE}
        className="sv-quote-depth-card sv-quote-depth-card--empty"
        testId="stock-view-depth-stack"
      >
        <QuoteHead detail={quoteDetail} symbol={depthSymbol} />
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
        <QuoteHead detail={quoteDetail} symbol={depthSymbol} />
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
      <QuoteHead detail={quoteDetail} symbol={depthSymbol} />
      <DepthAndTapeColumns
        symbol={depthSymbol}
        chips={captureReplay ? <CaptureReplayL2Chip clock={clock} /> : (
          <>
            <HaltEtaChip halt={detail.halt} />
            <ShortabilityChip ibkr={listingIbkr} />
          </>
        )}
        level2={showL2 ? (gap ? <HistoricalDepth depth={null} />
          : <Level2Module key={feedKey} symbol={depthSymbol} uiActive={uiActive} />) : null}
        tape={showTape ? (
          <TimeSalesModule
            key={feedKey}
            symbol={depthSymbol}
            embedded
            uiActive={uiActive}
            connectedText={captureReplay ? SIM_REPLAY_TAPE_STATUS : undefined}
            statusTitle={captureReplay ? SIM_CAPTURE_TAPE_TITLE : undefined}
            emptyLabel={gap ? SIM_CAPTURE_TAPE_NOT_RECORDED : undefined}
          />
        ) : null}
      />
    </StockViewModuleCard>
  );
}
