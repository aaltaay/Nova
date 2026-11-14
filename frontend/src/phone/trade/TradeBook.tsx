/**
 * Level 2 and Time & Sales on the phone (frozen mockup R2-Trade): the desk's book and the desk's tape,
 * as many rows of each as the box holds. Neither scrolls.
 *
 * The book's colours are the desk's montage: every order at one price shares a colour, and the next
 * price takes the next colour (ibkr/dasDepthTiers). Each book this component draws is reported to the
 * desk's view registry (`noteBookShown`), which is what an order says it was priced from (ADR 045).
 *
 * With the marks switch on (amendment 2026-11-13) the rows carry the desk's Level 2 marks and the depth chart
 * sits under them while every row of the book still fits beside it (`BookMarks.tsx`).
 */
import { memo, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { Clock, Pause } from 'lucide-react';
import { L2_BIG_ROW_BG, TICKER_TRADE_DEPTH_LEVELS } from '../../constants';
import { HALT_BADGE_LULD } from '../../constantGroups/halt_eta';
import { useBookWatchClock } from '../../ibkr/BookWatchParts';
import { priceKey, type BookWatchState } from '../../ibkr/bookWatch';
import type { BigRow } from '../../ibkr/bookWatchBig';
import { haltChipView } from '../../ibkr/haltEta';
import type { HaltSnapshot } from '../../types/ticker';
import { assignPriceTiers, tierBackground } from '../../ibkr/dasDepthTiers';
import { formatDepthPrice } from '../../ibkr/depthNumberFormat';
import { fmtTapeTime, formatTapePrice, formatTapeSize, tapeRowKey } from '../../ibkr/TapeRow';
import { tapePrintSetsPrice, type TapePrint } from '../../ibkr/tapeFeed';
import type { DepthBook, DepthLevel } from '../../ibkr/types';
import { noteBookShown } from '../../market_view';
import { plainPrice } from '../../utils/priceTick';
import { compact } from '../phoneFormat';
import { useRowsThatFit } from '../useRowsThatFit';
import {
  BigBannerChip, BigRowParts, DEPTH_STRIP_PX, DepthStrip, MarksLayer, rowMarkClass, sideMarks, type SideMarks,
} from './BookMarks';

const ROW_PX = 20;
/** A tape size is written whole up to here; past it the column has no room, and "12.5K" says enough. */
const TAPE_WHOLE_UNDER = 10_000;

function spreadWord(bid: number | null, ask: number | null): string {
  if (bid == null || ask == null) return 'spread —';
  return `spread ${plainPrice(Math.max(0, ask - bid), ask)}`;
}

/** A row half's marks: the big block it is part of, and whether a hidden or pulled price is outlined. */
interface HalfMarks {
  big?: BigRow;
  hidden: boolean;
  pulled: boolean;
}

const NO_MARKS: HalfMarks = { hidden: false, pulled: false };

function halfMarks(marks: SideMarks | null, level: DepthLevel | null, i: number): HalfMarks {
  if (!marks || !level) return NO_MARKS;
  const key = priceKey(level.price);
  const big = marks.big.get(i);
  const hidden = marks.hidden.has(key);
  const pulled = marks.pulled.has(key);
  return big || hidden || pulled ? { big, hidden, pulled } : NO_MARKS;
}

function halfStyle(level: DepthLevel | null, tier: number, marks: HalfMarks): CSSProperties | undefined {
  if (!level) return undefined;
  return { background: marks.big ? L2_BIG_ROW_BG : tierBackground(tier) };
}

const BookRow = memo(function BookRow({ bid, ask, bidTier, askTier, bidMarks = NO_MARKS, askMarks = NO_MARKS }: {
  bid: DepthLevel | null;
  ask: DepthLevel | null;
  bidTier: number;
  askTier: number;
  bidMarks?: HalfMarks;
  askMarks?: HalfMarks;
}) {
  return (
    <div className="ph-book__row">
      <div className={`is-bid ${rowMarkClass(bidMarks.big, bidMarks.hidden, bidMarks.pulled)}`} style={halfStyle(bid, bidTier, bidMarks)}>
        <span>{bid?.mm ?? ''}</span>
        <span>{bid ? compact(bid.size) : ''}</span>
        <b>{bid ? formatDepthPrice(bid.price) : ''}</b>
        <BigRowParts row={bidMarks.big} />
      </div>
      <div className={`is-ask ${rowMarkClass(askMarks.big, askMarks.hidden, askMarks.pulled)}`} style={halfStyle(ask, askTier, askMarks)}>
        <b>{ask ? formatDepthPrice(ask.price) : ''}</b>
        <span>{ask ? compact(ask.size) : ''}</span>
        <span>{ask?.mm ?? ''}</span>
        <BigRowParts row={askMarks.big} />
      </div>
    </div>
  );
});

export function TradeBook({ symbol, book, why, dim, watch = null, marksOn = false }: {
  symbol: string;
  book: DepthBook | null;
  /** Why there is no live book, in the desk's words. */
  why: string | null;
  /** The view is behind: the book is drawn faded. */
  dim: boolean;
  /** The line's book watch (`useIbkrDepth().watch`): the desk's verdicts the marks draw. */
  watch?: BookWatchState | null;
  /** The Settings switch: the desk's marks and the depth chart on this book. */
  marksOn?: boolean;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(boxRef, ROW_PX);
  // What left the book is read from depth: an L1-only book carries none (as on the desk's ladder).
  const marksWatch = marksOn && book && !book.l1_fallback ? watch : null;
  const nowMs = useBookWatchClock(marksWatch, Boolean(marksWatch));
  const bid = book?.bids[0]?.price ?? null;
  const ask = book?.asks[0]?.price ?? null;

  // ADR 045: which book version is on this screen. An order says it was priced from this one.
  useLayoutEffect(() => {
    if (book) noteBookShown(symbol, book.seq, bid, ask);
  }, [symbol, book, bid, ask]);

  const bids = book?.bids ?? [];
  const asks = book?.asks ?? [];
  const bidTiers = assignPriceTiers(bids);
  const askTiers = assignPriceTiers(asks);
  const longest = Math.max(bids.length, asks.length);
  // The depth chart takes the room under the rows only while every row of the book (up to the desk's ten) still
  // fits beside it, as the desk keeps its ten rows' floor under its own chart.
  const stripRows = Math.ceil((DEPTH_STRIP_PX + 4) / ROW_PX);
  const strip = marksOn && book != null && longest > 0 && fit - stripRows >= Math.min(longest, TICKER_TRADE_DEPTH_LEVELS);
  const rows = Math.min(strip ? fit - stripRows : fit, longest);
  const bidMarks = marksWatch ? sideMarks(marksWatch, 'bid', bids.slice(0, rows), nowMs) : null;
  const askMarks = marksWatch ? sideMarks(marksWatch, 'ask', asks.slice(0, rows), nowMs) : null;
  // The price column is as wide as the longest price on show ("4.81", "754.62", "0.3456"); the maker's name
  // takes what is left and is cut with an ellipsis when it must be.
  let priceChars = 4;
  for (let i = 0; i < rows; i += 1) {
    priceChars = Math.max(priceChars, bids[i] ? formatDepthPrice(bids[i].price).length : 0, asks[i] ? formatDepthPrice(asks[i].price).length : 0);
  }

  return (
    <div
      className="ph-book"
      data-dim={dim ? 'true' : 'false'}
      data-wide={priceChars > 5 ? 'true' : 'false'}
      data-testid="phone-book"
      style={{ '--ph-book-px': `${priceChars}ch` } as CSSProperties}
    >
      <div className="ph-book__top">
        <div className="is-bid">{bid != null ? formatDepthPrice(bid) : '—'} <i>BID</i></div>
        <span>{spreadWord(bid, ask)}</span>
        <div className="is-ask"><i>ASK</i> {ask != null ? formatDepthPrice(ask) : '—'}</div>
      </div>
      <div className="ph-book__cols">
        <div><span>MM</span><span>Size</span><span>Bid</span></div>
        <div><span>Ask</span><span>Size</span><span>MM</span></div>
        {bidMarks?.banner ? <BigBannerChip banner={bidMarks.banner} side="bid" /> : null}
        {askMarks?.banner ? <BigBannerChip banner={askMarks.banner} side="ask" /> : null}
      </div>
      <div className="ph-book__rows" ref={boxRef}>
        {!book || !rows ? (
          <div className="ph-book__wait" role="status" data-testid="phone-book-wait">{why ?? 'Opening Level 2…'}</div>
        ) : Array.from({ length: rows }, (_, i) => (
          <BookRow
            key={i}
            bid={bids[i] ?? null}
            ask={asks[i] ?? null}
            bidTier={bidTiers[i] ?? 0}
            askTier={askTiers[i] ?? 0}
            bidMarks={halfMarks(bidMarks, bids[i] ?? null, i)}
            askMarks={halfMarks(askMarks, asks[i] ?? null, i)}
          />
        ))}
        {bidMarks ? <MarksLayer marks={bidMarks.marks} side="bid" rowPx={ROW_PX} rows={rows} /> : null}
        {askMarks ? <MarksLayer marks={askMarks.marks} side="ask" rowPx={ROW_PX} rows={rows} /> : null}
        {strip && book ? <DepthStrip symbol={symbol} bids={bids.slice(0, rows)} asks={asks.slice(0, rows)} watch={marksWatch} /> : null}
      </div>
      {book && why ? <div className="ph-book__note" role="status">{why}</div> : null}
    </div>
  );
}

const TapeLine = memo(function TapeLine({ print }: { print: TapePrint }) {
  const when = fmtTapeTime(print.exchangeTs != null ? print.exchangeTs * 1000 : print.time);
  return (
    <div className="ph-tape__row" data-side={print.side ?? 'unknown'} data-price={tapePrintSetsPrice(print) ? 'true' : 'false'}>
      {/* Minutes and seconds: the hour is on the phone's own clock, and the column is narrow. */}
      <span>{when.slice(3)}</span>
      <b>{formatTapePrice(print.price)}</b>
      <span>{print.size < TAPE_WHOLE_UNDER ? formatTapeSize(print.size) : compact(print.size)}</span>
    </div>
  );
});

/**
 * The halt, in the desk's own words and on the desk's own clock (the Level 2 header's chip, `ibkr/haltEta`):
 * "LULD · 4:05 · 0:55 left", "Auction · 6:10 · 3:50 left", "NEWS · HALTED". It ticks once a second and sits
 * over the tape, where a halted stock otherwise only shows prints that stopped.
 */
function HaltLine({ halt }: { halt: HaltSnapshot }) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const view = haltChipView(halt, nowMs);
  if (!view) return null;
  const [head, ...rest] = view.label.split(' · ');
  return (
    <div className="ph-tape__halt" role="status" data-testid="phone-halt" data-kind={view.kind} data-phase={view.phase}>
      <b><Pause size={11} aria-hidden="true" /> {head === HALT_BADGE_LULD ? 'LULD halt' : head}</b>
      {rest.length ? <span>{rest.join(' · ')}</span> : null}
    </div>
  );
}

export function TradeTape({ prints, why, halt = null }: {
  prints: readonly TapePrint[];
  why: string | null;
  /** The stock's live halt, as the desk's ticker read carries it; null while it trades. */
  halt?: HaltSnapshot | null;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(boxRef, ROW_PX);
  const halted = halt?.halted ? halt : null;
  return (
    <div className="ph-tape" data-testid="phone-tape">
      <div className="ph-tape__cols"><span>Time</span><span>Price</span><span>Size</span></div>
      {halted ? <HaltLine halt={halted} /> : null}
      <div className="ph-tape__rows" ref={boxRef}>
        {!prints.length ? (
          <div className="ph-tape__wait" role="status">
            <Clock size={18} aria-hidden="true" />
            <span>{why ?? (halted ? 'No prints while it is halted.' : 'Tape waiting…')}</span>
          </div>
        ) : prints.slice(0, fit).map((p) => <TapeLine key={tapeRowKey(p)} print={p} />)}
      </div>
    </div>
  );
}
