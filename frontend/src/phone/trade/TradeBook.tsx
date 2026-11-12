/**
 * Level 2 and Time & Sales on the phone (frozen mockup R2-Trade): the desk's book and the desk's tape,
 * as many rows of each as the box holds. Neither scrolls.
 *
 * The book's colours are the desk's montage: every order at one price shares a colour, and the next
 * price takes the next colour (ibkr/dasDepthTiers). Each book this component draws is reported to the
 * desk's view registry (`noteBookShown`), which is what an order says it was priced from (ADR 045).
 */
import { memo, useLayoutEffect, useRef, type CSSProperties } from 'react';
import { Clock } from 'lucide-react';
import { assignPriceTiers, tierBackground } from '../../ibkr/dasDepthTiers';
import { formatDepthPrice } from '../../ibkr/depthNumberFormat';
import { fmtTapeTime, formatTapePrice, formatTapeSize, tapeRowKey } from '../../ibkr/TapeRow';
import { tapePrintSetsPrice, type TapePrint } from '../../ibkr/tapeFeed';
import type { DepthBook, DepthLevel } from '../../ibkr/types';
import { noteBookShown } from '../../market_view';
import { plainPrice } from '../../utils/priceTick';
import { compact } from '../phoneFormat';
import { useRowsThatFit } from '../useRowsThatFit';

const ROW_PX = 20;
/** A tape size is written whole up to here; past it the column has no room, and "12.5K" says enough. */
const TAPE_WHOLE_UNDER = 10_000;

function spreadWord(bid: number | null, ask: number | null): string {
  if (bid == null || ask == null) return 'spread —';
  return `spread ${plainPrice(Math.max(0, ask - bid), ask)}`;
}

const BookRow = memo(function BookRow({ bid, ask, bidTier, askTier }: {
  bid: DepthLevel | null;
  ask: DepthLevel | null;
  bidTier: number;
  askTier: number;
}) {
  return (
    <div className="ph-book__row">
      <div className="is-bid" style={bid ? { background: tierBackground(bidTier) } : undefined}>
        <span>{bid?.mm ?? ''}</span>
        <span>{bid ? compact(bid.size) : ''}</span>
        <b>{bid ? formatDepthPrice(bid.price) : ''}</b>
      </div>
      <div className="is-ask" style={ask ? { background: tierBackground(askTier) } : undefined}>
        <b>{ask ? formatDepthPrice(ask.price) : ''}</b>
        <span>{ask ? compact(ask.size) : ''}</span>
        <span>{ask?.mm ?? ''}</span>
      </div>
    </div>
  );
});

export function TradeBook({ symbol, book, why, dim }: {
  symbol: string;
  book: DepthBook | null;
  /** Why there is no live book, in the desk's words. */
  why: string | null;
  /** The view is behind: the book is drawn faded. */
  dim: boolean;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(boxRef, ROW_PX);
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
  const rows = Math.min(fit, Math.max(bids.length, asks.length));
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
      </div>
      <div className="ph-book__rows" ref={boxRef}>
        {!book || !rows ? (
          <div className="ph-book__wait" role="status" data-testid="phone-book-wait">{why ?? 'Opening Level 2…'}</div>
        ) : Array.from({ length: rows }, (_, i) => (
          <BookRow key={i} bid={bids[i] ?? null} ask={asks[i] ?? null} bidTier={bidTiers[i] ?? 0} askTier={askTiers[i] ?? 0} />
        ))}
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

export function TradeTape({ prints, why }: { prints: readonly TapePrint[]; why: string | null }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(boxRef, ROW_PX);
  return (
    <div className="ph-tape" data-testid="phone-tape">
      <div className="ph-tape__cols"><span>Time</span><span>Price</span><span>Size</span></div>
      <div className="ph-tape__rows" ref={boxRef}>
        {!prints.length ? (
          <div className="ph-tape__wait" role="status">
            <Clock size={18} aria-hidden="true" />
            <span>{why ?? 'Tape waiting…'}</span>
          </div>
        ) : prints.slice(0, fit).map((p) => <TapeLine key={tapeRowKey(p)} print={p} />)}
      </div>
    </div>
  );
}
