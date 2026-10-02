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
import { priceKey, pulledHere, pullMarks, type BookWatchState, type PulledHere } from './bookWatch';
import { hiddenHere, hiddenMarks } from './bookWatchHidden';
import { PullMarksAt, PullsStrip, useBookWatchClock } from './BookWatchParts';
import { placeMarkers, splitMarkers, type DepthMarker, type PlacedMarker } from './depthMarkers';
import {
  depthEmptyMessage,
  depthLiveBadge,
  depthLiveBadgeText,
} from './depthUiStatus';
import { depthLentText } from './lentWords';
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
  /** A Trader tab's Level 2: its line may be lent while the tab is hidden (ADR 044 decision 6). */
  traderTab?: boolean;
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
const NO_PULLED_HERE: ReadonlyMap<string, PulledHere> = new Map();

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
 * the same length on the bid and the ask. `markers` are this side's plan levels;
 * `watch` is the book watcher's verdicts on the live line (bookWatch.ts), aged by `nowMs`.
 */
export function MontageSide({
  side,
  levels,
  peak,
  markers = [],
  watch = null,
  nowMs = 0,
}: {
  side: 'bid' | 'ask';
  levels: DepthLevel[];
  peak: number;
  markers?: readonly DepthMarker[];
  watch?: BookWatchState | null;
  nowMs?: number;
}) {
  const tiers = assignPriceTiers(levels);
  const padded = padLevels(levels, TICKER_TRADE_DEPTH_LEVELS);
  const isBid = side === 'bid';
  const shown = Math.min(levels.length, TICKER_TRADE_DEPTH_LEVELS);
  const rows = levels.slice(0, shown);
  const placed = markers.length ? placeMarkers(side, rows, markers) : [];
  // A hidden seller or buyer's mark comes first at its place; one that holds outlines its rows.
  const marks = watch && shown ? [...hiddenMarks(watch, side, rows, nowMs), ...pullMarks(watch, side, rows, nowMs)] : [];
  const here = watch && shown ? pulledHere(watch, side, rows, nowMs) : NO_PULLED_HERE;
  const hiddenAt = watch && shown ? hiddenHere(watch, side, rows, nowMs) : NO_PULLED_HERE;
  const lines = (before: number, at: 'edge' | 'first' | 'end' | 'flow') =>
    placed.filter(m => m.before === before).map(m => <MarkerLine key={`mk-${m.id}`} marker={m} at={at} />);
  const pulls = (before: number, at: 'head' | 'edge' | 'end') => (
    <PullMarksAt marks={marks.filter(m => m.before === before)} at={at} />
  );
  // Inside row i: the levels between it and the row above; the last shown row also carries the levels past it.
  // What left above the book (a level better than the inside now) is marked over the column head instead,
  // so it never covers the inside row.
  const inRow = (i: number) => (i >= shown ? null : (
    <>
      {lines(i, i === 0 ? 'first' : 'edge')}
      {i > 0 && pulls(i, 'edge')}
      {i === shown - 1 && lines(shown, 'end')}
      {i === shown - 1 && pulls(shown, 'end')}
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
      {shown > 0 && pulls(0, 'head')}
      {padded.map((level, i) => {
        const tier = level != null ? (tiers[i] ?? 0) : 0;
        const bg = level ? tierBackground(tier) : 'transparent';
        const gauge = level ? sizeGaugePct(level.size, peak) : 0;
        const pulledAt = level ? here.get(priceKey(level.price)) : undefined;
        const hiddenRow = level ? hiddenAt.get(priceKey(level.price)) : undefined;
        const rowTip = hiddenRow ?? pulledAt;
        return (
          <div
            key={`${side}-${i}`}
            className={`das-l2-row ${level ? 'das-l2-row--tiered' : 'das-l2-row--empty'}${pulledAt ? ' das-l2-row--pulled-here' : ''}${hiddenRow ? ' das-l2-row--hidden-here' : ''}`}
            style={{ backgroundColor: bg }}
            {...(rowTip ? tipProps(rowTip.tip, rowTip.title) : {})}
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

export function DepthLadder({ symbol, uiActive = true, markers, traderTab = false }: Props) {
  useRenderCount('DepthLadder');
  const { book, connected, l1Fallback, error, watch, lent } = useIbkrDepth(symbol, uiActive, { traderTab });
  const { setTopOfBook } = useTopOfBook();
  // What left the book (ADR 033 amendment): the watcher reads depth, so an L1-only book carries none.
  const ladderWatch = l1Fallback ? null : watch;
  const nowMs = useBookWatchClock(ladderWatch, uiActive);

  const topBid = book?.bids[0]?.price ?? null;
  const topAsk = book?.asks[0]?.price ?? null;
  const depthSubscribed = book != null && connected;
  useEffect(() => {
    if (!symbol || !uiActive) {
      setTopOfBook(null);
      return;
    }
    setTopOfBook({ symbol: symbol.toUpperCase(), bid: topBid, ask: topAsk, depthSubscribed });
  }, [symbol, uiActive, topBid, topAsk, depthSubscribed, setTopOfBook]);
  // Cleared when this ladder goes or changes symbol -- not between two books, which used to publish
  // null and then the book again on every update and redraw every reader twice.
  useEffect(() => {
    if (!symbol || !uiActive) return;
    return () => setTopOfBook(null);
  }, [symbol, uiActive, setTopOfBook]);

  if (!symbol) {
    return <div className="ibkr-depth-empty">Enter a symbol to view the order book.</div>;
  }

  // The line went to one of Nova's setups (ADR 044): say whose, and when it comes back.
  if (lent) {
    return (
      <div className="ibkr-depth-empty ibkr-depth-lent" data-testid="ibkr-depth-lent" role="status">
        {depthLentText(lent)}
      </div>
    );
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
      <PullsStrip watch={ladderWatch} />
      <div className="das-l2-montage">
        <MontageSide side="bid" levels={book.bids} peak={peak} markers={sides.bid} watch={ladderWatch} nowMs={nowMs} />
        <MontageSide side="ask" levels={book.asks} peak={peak} markers={sides.ask} watch={ladderWatch} nowMs={nowMs} />
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
