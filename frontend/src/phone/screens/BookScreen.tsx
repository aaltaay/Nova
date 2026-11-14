/**
 * The Level 2 read (ADR 070 amendment 2026-11-13, mockup v2: the page the depth chart under the book opens). One
 * stock's book on one screen that never scrolls: the spread, the desk's depth chart large (a touch reads a price,
 * as the desk's hover does), one card per mark the book watcher calls -- a big seller or buyer, a hidden seller or
 * buyer, what was pulled or taken -- and each side's last minute of pulled against traded.
 *
 * It holds the same Level 2 line as the Trade screen (`useIbkrDepth`), and every word is the desk's: the cards are
 * the marks' own titles and hovers (`ibkr/bookWatch*`). Nothing is sent from here.
 */
import { useMemo, useRef, useState } from 'react';
import { TICKER_TRADE_DEPTH_LEVELS } from '../../constants';
import { Level2DepthChart } from '../../ibkr/Level2DepthChart';
import { useBookWatchClock } from '../../ibkr/BookWatchParts';
import { pullsLine, type BookSide, type BookWatchState } from '../../ibkr/bookWatch';
import { formatDepthPrice } from '../../ibkr/depthNumberFormat';
import type { DepthLevel } from '../../ibkr/types';
import { useIbkrDepth } from '../../ibkr/useIbkrDepth';
import { plainPrice } from '../../utils/priceTick';
import { BackButton, PhoneScreen, VenuePill } from '../PhoneChrome';
import { go } from '../phoneRoute';
import { sideMarks } from '../trade/BookMarks';
import { useLevel2Marks } from '../trade/level2MarksSwitch';
import { useRowsThatFit } from '../useRowsThatFit';
import '../../ibkr/level2DepthChart.css';
import '../trade/bookMarks.css';
import './book.css';

/** One card's height: a title line and two lines of the desk's words. */
const CARD_PX = 58;
/** The desk's hover line, for a phone: a tap on the chart reads a price. */
const TAP_HINT = 'Tap a price: what rests up to it.';

export interface ReadCard {
  id: string;
  kind: 'big' | 'hidden' | 'pulled' | 'approach' | 'traded';
  side: BookSide;
  title: string;
  /** The desk's hover, line by line; the card shows the first two. */
  lines: string[];
  opacity: number;
}

/** Every mark the watcher calls on the rows the desk shows, as cards: big first, then hidden, then what left. */
export function readCards(watch: BookWatchState | null, bids: readonly DepthLevel[], asks: readonly DepthLevel[], nowMs: number): ReadCard[] {
  if (!watch) return [];
  const out: ReadCard[] = [];
  for (const side of ['ask', 'bid'] as const) {
    const rows = (side === 'ask' ? asks : bids).slice(0, TICKER_TRADE_DEPTH_LEVELS);
    const m = sideMarks(watch, side, rows, nowMs);
    if (m.banner) {
      out.push({
        id: `${side}-big`,
        kind: 'big',
        side,
        title: m.banner.parts.map((p) => `${p.sep}${p.text}`).join(''),
        lines: m.banner.tip.split('\n'),
        opacity: m.banner.opacity,
      });
    }
    for (const mark of m.marks) {
      out.push({ id: mark.id, kind: mark.kind, side, title: mark.title, lines: mark.tip.split('\n'), opacity: mark.opacity });
    }
  }
  const order: Record<ReadCard['kind'], number> = { big: 0, hidden: 1, approach: 2, pulled: 3, traded: 4 };
  return out.sort((a, b) => order[a.kind] - order[b.kind]);
}

function LastMinute({ watch }: { watch: BookWatchState | null }) {
  const sides = (['bid', 'ask'] as const).map((side) => ({ side, line: pullsLine(watch, side) }));
  if (sides.some((s) => !s.line)) return null;
  if (!sides[0].line?.watching) {
    return <div className="ph-read__minute is-off" role="status">{sides[0].line?.tip.split('\n')[0]}</div>;
  }
  return (
    <div className="ph-read__minute" data-testid="phone-read-minute">
      {sides.map(({ side, line }) => (
        <div key={side} data-side={side} data-warn={line?.warn ? 'true' : 'false'}>
          <b>{side === 'bid' ? 'Bid side' : 'Ask side'}</b>
          <span>pulled <em>{line?.pulled.replace('✕ ', '')}</em></span>
          <span>traded <em>{line?.traded.replace('✓ ', '')}</em></span>
          {line?.hidden ? <span>hidden <em>{line.hidden.replace('◆ ', '')}</em></span> : null}
        </div>
      ))}
    </div>
  );
}

export function BookScreen({ symbol }: { symbol: string }) {
  const marksOn = useLevel2Marks();
  const depth = useIbkrDepth(symbol, true);
  const book = depth.book;
  const watch = book && !book.l1_fallback ? depth.watch : null;
  const nowMs = useBookWatchClock(watch, Boolean(watch));
  const bids = useMemo(() => book?.bids ?? [], [book]);
  const asks = useMemo(() => book?.asks ?? [], [book]);
  const bid = bids[0]?.price ?? null;
  const ask = asks[0]?.price ?? null;
  const cards = useMemo(() => (marksOn ? readCards(watch, bids, asks, nowMs) : []), [marksOn, watch, bids, asks, nowMs]);
  const boxRef = useRef<HTMLDivElement>(null);
  const perPage = useRowsThatFit(boxRef, CARD_PX + 6);
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(cards.length / perPage));
  const at = Math.min(page, pages - 1);
  const why = depth.laneWait?.plain ?? depth.error ?? (book?.l1_fallback ? 'IBKR sent no Level 2 for this stock: this is the top of book only.' : null);

  return (
    <PhoneScreen
      name="book"
      tab="trade"
      header={(
        <div className="ph-head has-back">
          <BackButton to={{ screen: 'trade', symbol }} label="Back to Trade" />
          <div className="ph-head__title">
            <button type="button" className="ph-tickerword" aria-label={`Open ${symbol}'s stock page`} onClick={() => go({ screen: 'stock', symbol })}>{symbol}</button>
            {' · Level 2 read'}
          </div>
          <div className="ph-grow" />
          <VenuePill />
        </div>
      )}
    >
      <div className="ph-read ph-book-read" data-testid="phone-book-read">
        <div className="ph-read__spread">
          <span className="is-bid">{bid != null ? formatDepthPrice(bid) : '—'} <i>BID</i></span>
          <span className="ph-read__pill">spread {bid != null && ask != null ? plainPrice(Math.max(0, ask - bid), ask) : '—'}</span>
          <span className="is-ask"><i>ASK</i> {ask != null ? formatDepthPrice(ask) : '—'}</span>
        </div>
        <div className="ph-read__chart">
          {book && (bids.length || asks.length)
            ? <Level2DepthChart bids={bids} asks={asks} watch={watch} alwaysOn hint={TAP_HINT} />
            : <div className="ph-read__wait" role="status">{why ?? 'Opening Level 2…'}</div>}
        </div>
        {!marksOn ? (
          <div className="ph-read__note" role="status">The Level 2 marks are off on this phone. Settings turns them on.</div>
        ) : (
          <>
            <div className="ph-label ph-read__label">In the book now</div>
            <div className="ph-read__cards" ref={boxRef}>
              {cards.length ? cards.slice(at * perPage, (at + 1) * perPage).map((c) => (
                <div key={c.id} className="ph-read__card" data-kind={c.kind} data-side={c.side} style={{ opacity: Math.max(0.45, c.opacity) }} data-testid={`phone-read-${c.kind}`}>
                  <b>{c.title}</b>
                  <span>{c.lines.slice(0, 2).join(' ')}</span>
                </div>
              )) : (
                <div className="ph-read__quiet" role="status">
                  {watch?.watching === false ? (watch.reason ?? 'Nova is not reading this book yet.') : 'Nothing called on this book right now: no big seller or buyer, no hidden size, nothing pulled.'}
                </div>
              )}
            </div>
            {pages > 1 ? (
              <div className="ph-read__pager">
                <button type="button" className="ph-pill-btn" disabled={at === 0} data-why="This is the first page." onClick={() => setPage(at - 1)}>‹ Prev</button>
                <span>{at + 1} / {pages}</span>
                <button type="button" className="ph-pill-btn" disabled={at >= pages - 1} data-why="This is the last page." onClick={() => setPage(at + 1)}>Next ›</button>
              </div>
            ) : null}
            <div className="ph-label ph-read__label">Last minute</div>
            <LastMinute watch={watch} />
          </>
        )}
        <div className="ph-read__foot">The desk's own read of the book. A description, not a buy or sell signal.</div>
      </div>
    </PhoneScreen>
  );
}
