/** The stock read on the Trader rail, between the quote and Level 2 (ADR 036): the plan box and the
 * seven tiles -- or one line saying why there is no read. On `auto` the plan opens whole only while
 * the quote card has room for it and Level 2 both. */
import { useEffect, useRef, useState } from 'react';
import { STOCK_READ_PLAN_OPEN_MIN_PX } from './constants';
import { PlanCard } from './PlanCard';
import { ReadStrip } from './ReadStrip';
import { useStockReadContext } from './StockReadContext';
import './stockRead.css';

/** The height of the card this block sits in (its parent), as it changes. */
function useParentHeight(ref: React.RefObject<HTMLElement | null>): number | null {
  const [height, setHeight] = useState<number | null>(null);
  useEffect(() => {
    const parent = ref.current?.parentElement;
    if (!parent) return;
    setHeight(parent.getBoundingClientRect().height);
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setHeight(e.contentRect.height);
    });
    ro.observe(parent);
    return () => ro.disconnect();
  }, [ref]);
  return height;
}

export function StockReadRail() {
  const ctx = useStockReadContext();
  const ref = useRef<HTMLDivElement>(null);
  const cardHeight = useParentHeight(ref);
  if (!ctx) return null;
  const { read } = ctx;
  let note: string | null = null;
  if (ctx.replay) note = 'The bot\'s read is today\'s live stock; this desk is replaying another moment.';
  else if (read.unavailable && !read.data) note = 'This backend has no stock read yet: reload the backend.';
  else if (!read.data) note = read.error ?? `Reading ${ctx.symbol}…`;
  if (note) {
    return (
      <div className="sr-rail sr-rail--note" ref={ref} data-testid="stock-read-rail">
        <p className="sr-rail__note" data-testid="stock-read-rail-note">{note}</p>
      </div>
    );
  }
  // Unknown height (no layout, e.g. a test) counts as room.
  const roomy = cardHeight === null || cardHeight === 0 || cardHeight >= STOCK_READ_PLAN_OPEN_MIN_PX;
  return (
    <div className="sr-rail" ref={ref} data-testid="stock-read-rail">
      <PlanCard ctx={ctx} roomy={roomy} />
      <ReadStrip ctx={ctx} />
      {read.error && <p className="sr-rail__stale" data-testid="stock-read-stale">{read.error}: showing the last read.</p>}
    </div>
  );
}
