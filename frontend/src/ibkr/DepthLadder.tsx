import { useEffect, type CSSProperties } from 'react';
import {
  L2_DAS_HEADERS,
  L2_DAS_MM_FALLBACK,
  L2_DAS_SIZE_BAR,
  L2_HEURISTIC_ASK_LABEL,
  L2_HEURISTIC_BID_LABEL,
  L2_HEURISTIC_IDLE_LABEL,
  L2_HEURISTIC_SPREAD_LABEL,
  L2_HEURISTIC_TITLE,
  L2_OVERNIGHT_BOOK_HINT,
  TICKER_TRADE_DEPTH_LEVELS,
} from '../constants';
import { useTopOfBook } from '../hotkeys/TopOfBookContext';
import { assignPriceTiers, maxSize, padLevels, tierBackground } from './dasDepthTiers';
import { isOvernightOnlyBook } from './depthBookGuards';
import {
  depthEmptyMessage,
  depthLiveBadge,
  depthLiveBadgeText,
} from './depthUiStatus';
import { computeL2Heuristics } from './l2Heuristics';
import { useIbkrDepth } from './useIbkrDepth';
import type { DepthLevel } from './types';
import { useRenderCount } from '../perf/useRenderCount';

interface Props {
  symbol: string | null;
  /** False on live-but-hidden trader tabs -- keep WS, pause ladder/TOB paint. */
  uiActive?: boolean;
}

function fmtPrice(p: number | null | undefined) {
  if (p == null) return '';
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function fmtSize(s: number | null | undefined) {
  if (s == null) return '';
  return s.toLocaleString('en-US');
}

function mmLabel(level: DepthLevel | null): string {
  if (!level) return '';
  const raw = (level.mm || '').trim();
  return raw || L2_DAS_MM_FALLBACK;
}

function sizeBarStyle(
  size: number,
  max: number,
  color: string,
  side: 'bid' | 'ask',
  tierBg: string,
): CSSProperties {
  if (max <= 0 || size <= 0) {
    return { backgroundColor: tierBg };
  }
  const pct = Math.min(100, Math.round((size / max) * 100));
  // Grow from the price column toward MM (bid: right-to-left, ask: left-to-right).
  const dir = side === 'bid' ? 'to left' : 'to right';
  return {
    backgroundImage: `linear-gradient(${dir}, ${color} ${pct}%, transparent ${pct}%), linear-gradient(${tierBg}, ${tierBg})`,
  };
}

/** One side of the DAS-style montage; historical replay renders it with no levels. */
export function MontageSide({
  side,
  levels,
}: {
  side: 'bid' | 'ask';
  levels: DepthLevel[];
}) {
  const tiers = assignPriceTiers(levels);
  const padded = padLevels(levels, TICKER_TRADE_DEPTH_LEVELS);
  const peak = maxSize(levels);
  const isBid = side === 'bid';

  return (
    <div className={`das-l2-side das-l2-side--${side}`}>
      <div className="das-l2-colhead">
        {isBid ? (
          <>
            <span>{L2_DAS_HEADERS.bidMm}</span>
            <span>{L2_DAS_HEADERS.bidSize}</span>
            <span>{L2_DAS_HEADERS.bidPrice}</span>
          </>
        ) : (
          <>
            <span>{L2_DAS_HEADERS.askPrice}</span>
            <span>{L2_DAS_HEADERS.askSize}</span>
            <span>{L2_DAS_HEADERS.askMm}</span>
          </>
        )}
      </div>
      {padded.map((level, i) => {
        const tier = level != null ? (tiers[i] ?? 0) : 0;
        const bg = level ? tierBackground(tier) : 'transparent';
        const bar = level
          ? sizeBarStyle(level.size, peak, L2_DAS_SIZE_BAR, side, bg)
          : undefined;
        return (
          <div
            key={`${side}-${i}`}
            className={`das-l2-row ${level ? 'das-l2-row--tiered' : 'das-l2-row--empty'}`}
            style={bar ?? { backgroundColor: bg }}
          >
            {isBid ? (
              <>
                <span className="das-l2-mm">{mmLabel(level)}</span>
                <span className="das-l2-size">{fmtSize(level?.size)}</span>
                <span className="das-l2-price">{fmtPrice(level?.price)}</span>
              </>
            ) : (
              <>
                <span className="das-l2-price">{fmtPrice(level?.price)}</span>
                <span className="das-l2-size">{fmtSize(level?.size)}</span>
                <span className="das-l2-mm">{mmLabel(level)}</span>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function DepthLadder({ symbol, uiActive = true }: Props) {
  useRenderCount('DepthLadder');
  const { book, connected, l1Fallback, error } = useIbkrDepth(symbol, uiActive);
  const { setTopOfBook } = useTopOfBook();

  useEffect(() => {
    if (!symbol || !uiActive) {
      if (!uiActive) setTopOfBook(null);
      if (!symbol) setTopOfBook(null);
      return;
    }
    const bid = book?.bids[0]?.price ?? null;
    const ask = book?.asks[0]?.price ?? null;
    setTopOfBook({
      symbol: symbol.toUpperCase(),
      bid,
      ask,
      depthSubscribed: book != null && connected,
    });
    return () => setTopOfBook(null);
  }, [symbol, book, connected, setTopOfBook, uiActive]);

  if (!symbol) {
    return <div className="ibkr-depth-empty">Enter a symbol to view the order book.</div>;
  }

  // Keep the last book on screen across brief WS reconnects. Only show the
  // full "Connecting…" placeholder when we have nothing to display yet.
  if (!book) {
    return (
      <div className="ibkr-depth-empty">
        {depthEmptyMessage(symbol, connected, error)}
      </div>
    );
  }

  const { askStacked, bidHeavy, wideSpread } = computeL2Heuristics(book);
  const bestBid = book.bids[0]?.price;
  const bestAsk = book.asks[0]?.price;
  const spread =
    bestBid != null && bestAsk != null ? Math.abs(bestAsk - bestBid) : null;
  const liveBadge = depthLiveBadge(connected, error, l1Fallback);
  const liveBadgeText = depthLiveBadgeText(liveBadge);
  const overnightOnly = isOvernightOnlyBook(book);

  return (
    <div className="das-l2">
      {liveBadgeText && (
        <div className="ibkr-depth-fallback-badge" title={liveBadgeText}>
          {liveBadgeText}
        </div>
      )}
      {overnightOnly && !l1Fallback && (
        <div className="ibkr-depth-fallback-badge" title={L2_OVERNIGHT_BOOK_HINT}>
          {L2_OVERNIGHT_BOOK_HINT}
        </div>
      )}
      <div className="ibkr-depth-heuristics" title={L2_HEURISTIC_TITLE}>
        {askStacked && (
          <span className="ibkr-heuristic-badge ibkr-heuristic-ask">{L2_HEURISTIC_ASK_LABEL}</span>
        )}
        {bidHeavy && (
          <span className="ibkr-heuristic-badge ibkr-heuristic-bid">{L2_HEURISTIC_BID_LABEL}</span>
        )}
        {wideSpread && (
          <span className="ibkr-heuristic-badge ibkr-heuristic-spread">{L2_HEURISTIC_SPREAD_LABEL}</span>
        )}
        {!askStacked && !bidHeavy && !wideSpread && (
          <span className="ibkr-heuristic-badge ibkr-heuristic-idle">{L2_HEURISTIC_IDLE_LABEL}</span>
        )}
      </div>
      <div className="das-l2-montage">
        <MontageSide side="bid" levels={book.bids} />
        <MontageSide side="ask" levels={book.asks} />
      </div>
      {spread != null && (
        <div className="das-l2-spread">
          spread {fmtPrice(spread)}
          {bestBid != null && bestAsk != null && (
            <span className="das-l2-bbo">
              {' '}
              · {fmtPrice(bestBid)} × {fmtPrice(bestAsk)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
