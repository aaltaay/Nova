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
import {
  assignPriceTiers,
  bookPeak,
  padLevels,
  sizeGaugePct,
  tierBackground,
} from './dasDepthTiers';
import { isOvernightOnlyBook } from './depthBookGuards';
import { placeMarkers, splitMarkers, type DepthMarker, type PlacedMarker } from './depthMarkers';
import {
  depthEmptyMessage,
  depthLiveBadge,
  depthLiveBadgeText,
} from './depthUiStatus';
import { computeL2Heuristics } from './l2Heuristics';
import { useIbkrDepth } from './useIbkrDepth';
import type { DepthLevel } from './types';
import { useRenderCount } from '../perf/useRenderCount';
import { tipProps } from '../ux';

interface Props {
  symbol: string | null;
  /** False on live-but-hidden trader tabs -- keep WS, pause ladder/TOB paint. */
  uiActive?: boolean;
  /** The plan's ENTRY / STOP / TARGET, drawn where they sit in the book (ADR 037). */
  markers?: readonly DepthMarker[];
}

function fmtPrice(p: number | null | undefined) {
  if (p == null) return '';
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function fmtSize(s: number | null | undefined) {
  if (s == null) return '';
  return s.toLocaleString('en-US');
}

const NO_MARKERS: { bid: DepthMarker[]; ask: DepthMarker[] } = { bid: [], ask: [] };

function mmLabel(level: DepthLevel | null): string {
  if (!level) return '';
  const raw = (level.mm || '').trim();
  return raw || L2_DAS_MM_FALLBACK;
}

/**
 * The plan's level between the book's rows (solid when an order stands behind it). It is drawn over the
 * boundary between two rows, never as a row of its own: the Trader rail's ladder has a fixed height, and a
 * row more would push the book's last rows -- and a level past them -- out of sight.
 */
function MarkerLine({ marker, at }: { marker: PlacedMarker; at: 'edge' | 'first' | 'end' | 'flow' }) {
  return (
    <div
      className={`das-l2-marker das-l2-marker--${at} das-l2-marker--${marker.working ? 'working' : 'plan'}`}
      style={{ ['--das-l2-marker' as string]: marker.color } as CSSProperties}
      data-testid={`l2-marker-${marker.id}`}
      {...tipProps(marker.tip, marker.label)}
    >
      <span className="das-l2-marker__tag">
        {marker.label}
        {marker.beyond ? ' ↓' : ''}
      </span>
    </div>
  );
}

/**
 * One side of the DAS-style montage; historical replay renders it with no levels.
 * `peak` is the largest size on the whole book (`bookPeak`), so a size gauge is
 * the same length on the bid and the ask. `markers` are this side's plan levels.
 */
export function MontageSide({
  side,
  levels,
  peak,
  markers = [],
}: {
  side: 'bid' | 'ask';
  levels: DepthLevel[];
  peak: number;
  markers?: readonly DepthMarker[];
}) {
  const tiers = assignPriceTiers(levels);
  const padded = padLevels(levels, TICKER_TRADE_DEPTH_LEVELS);
  const isBid = side === 'bid';
  const shown = Math.min(levels.length, TICKER_TRADE_DEPTH_LEVELS);
  const placed = markers.length ? placeMarkers(side, levels.slice(0, shown), markers) : [];
  const lines = (before: number, at: 'edge' | 'first' | 'end' | 'flow') =>
    placed.filter(m => m.before === before).map(m => <MarkerLine key={`mk-${m.id}`} marker={m} at={at} />);
  // Inside row i: the levels between it and the row above; the last shown row also carries the levels past it.
  const inRow = (i: number) => (i >= shown ? null : (
    <>
      {lines(i, i === 0 ? 'first' : 'edge')}
      {i === shown - 1 && lines(shown, 'end')}
    </>
  ));

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
      {shown === 0 && lines(0, 'flow')}
      {padded.map((level, i) => {
        const tier = level != null ? (tiers[i] ?? 0) : 0;
        const bg = level ? tierBackground(tier) : 'transparent';
        const gauge = level ? sizeGaugePct(level.size, peak) : 0;
        return (
          <div
            key={`${side}-${i}`}
            className={`das-l2-row ${level ? 'das-l2-row--tiered' : 'das-l2-row--empty'}`}
            style={{ backgroundColor: bg }}
          >
            {inRow(i)}
            {gauge > 0 && (
              <span
                className="das-l2-gauge"
                style={{ width: `${gauge}%`, backgroundColor: L2_DAS_SIZE_BAR }}
                aria-hidden="true"
              />
            )}
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

export function DepthLadder({ symbol, uiActive = true, markers }: Props) {
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
  const peak = bookPeak(book.bids, book.asks);
  const sides = markers?.length ? splitMarkers(markers, book.bids, book.asks) : NO_MARKERS;

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
        <MontageSide side="bid" levels={book.bids} peak={peak} markers={sides.bid} />
        <MontageSide side="ask" levels={book.asks} peak={peak} markers={sides.ask} />
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
