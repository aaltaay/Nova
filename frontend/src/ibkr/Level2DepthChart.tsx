/**
 * The depth chart over the book (operator ask, 2026-11-13, mockup v1): the shares the Level 2 shows, stacked
 * outward from the inside -- bids to the left, offers to the right, both on one scale, so a tall step is a
 * wall. Each side's total, in shares and dollars, sits at its far edge. A big seller or buyer the watcher is
 * following is marked on its step. Hover a price for what rests between the inside and there.
 *
 * Drawn only while the operator's switch is on (the pane's right-click menu), and only from the rows on
 * screen: one step per price, nothing past the last row.
 */
import { useState, type CSSProperties, type MouseEvent } from 'react';
import { L2_DEPTH_CHART_HINT, L2_DEPTH_CHART_LABELS, TICKER_TRADE_DEPTH_LEVELS } from '../constants';
import { markPrice, markShares, markWhole, type BookSide, type BookWatchState } from './bookWatch';
import { depthDollars, depthSteps, useLevel2DepthChart, type DepthStep } from './level2DepthSwitch';
import type { DepthLevel } from './types';

interface Props {
  bids: readonly DepthLevel[];
  asks: readonly DepthLevel[];
  /** The line's book watch: its big sellers and buyers still holding are marked on their steps. */
  watch?: BookWatchState | null;
  /**
   * Drawn whatever the desk's switch says: a page that shows the chart as its own choice (the phone's book,
   * ADR 070 amendment 2026-11-13). The desk leaves it off and reads its right-click switch.
   */
  alwaysOn?: boolean;
  /** The read line before a price is pointed at: the phone, which has no hover, says a tap. */
  hint?: string;
}

const HALF = 50;
/** The tallest step stops short of the top, so its line is never clipped. */
const TOP = 6;
const PRICE_EPS = 1e-9;
/** Past this share of the width a seller's words would run off the pane: pin them to the edge. */
const TAG_PIN = 62;

/** What rests between the inside and one step, as the hover line says it. */
export function depthReadout(side: BookSide, step: DepthStep): string {
  const reach = side === 'ask' ? L2_DEPTH_CHART_LABELS.askReach : L2_DEPTH_CHART_LABELS.bidReach;
  return `${markWhole(step.shares)} · ${depthDollars(step.dollars)} ${reach} ${markPrice(step.price)} `
    + `(${markWhole(step.size)} at that price)`;
}

/** Where a wall's words go: beside its line, on the outer side; pinned to the pane's edge when near it. */
function tagPlace(side: BookSide, x: number, top: number): CSSProperties {
  const far = side === 'ask' ? x > TAG_PIN : x < 100 - TAG_PIN;
  if (side === 'ask') return far ? { right: 0, top: `${top}%` } : { left: `${x}%`, top: `${top}%` };
  return far ? { left: 0, top: `${top}%` } : { right: `${100 - x}%`, top: `${top}%` };
}

/** A side's area: from the middle outward, one cell per price, each at its running total. */
function area(steps: readonly DepthStep[], dir: 1 | -1, y: (shares: number) => number): string {
  if (!steps.length) return '';
  const cell = HALF / steps.length;
  let d = `M${HALF} 100`;
  steps.forEach((s, i) => {
    const x = HALF + dir * i * cell;
    d += ` L${x} ${y(s.shares)} L${x + dir * cell} ${y(s.shares)}`;
  });
  return `${d} L${HALF + dir * HALF} 100 Z`;
}

export function Level2DepthChart({ bids, asks, watch = null, alwaysOn = false, hint = L2_DEPTH_CHART_HINT }: Props) {
  const on = useLevel2DepthChart() || alwaysOn;
  // The pointer's place only: its words are read from the book on screen at each draw, never kept.
  const [hoverX, setHoverX] = useState<number | null>(null);
  if (!on) return null;
  // The rows the ladder draws (MontageSide), no more: a Sim book of several venues can hold more.
  const rows = (levels: readonly DepthLevel[]) => depthSteps(levels.slice(0, TICKER_TRADE_DEPTH_LEVELS));
  const sides: Record<BookSide, DepthStep[]> = { bid: rows(bids), ask: rows(asks) };
  if (!sides.bid.length && !sides.ask.length) return null;
  const total = (side: BookSide) => sides[side][sides[side].length - 1];
  const max = Math.max(total('bid')?.shares ?? 0, total('ask')?.shares ?? 0);
  const y = (shares: number) => 100 - (shares / max) * (100 - TOP);

  const walls = (watch?.big ?? []).flatMap((w) => {
    if (w.state !== 'holding') return [];
    const steps = sides[w.side];
    const i = steps.findIndex((s) => Math.abs(s.price - w.price) < PRICE_EPS);
    if (i < 0) return [];
    const dir = w.side === 'ask' ? 1 : -1;
    const x = HALF + dir * i * (HALF / steps.length);
    return [{ id: w.id, side: w.side, x, from: y(steps[i].shares - steps[i].size), to: y(steps[i].shares),
      text: `${L2_DEPTH_CHART_LABELS[w.side === 'ask' ? 'seller' : 'buyer']} ${markPrice(w.price)} · ${markShares(steps[i].size)}` }];
  });

  const onMove = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (!(box.width > 0)) return;
    setHoverX(Math.min(100, Math.max(0, ((event.clientX - box.left) / box.width) * 100)));
  };
  const hoverSide: BookSide = hoverX != null && hoverX >= HALF ? 'ask' : 'bid';
  const hoverSteps = sides[hoverSide];
  const hoverStep = hoverX == null || !hoverSteps.length ? null
    : hoverSteps[Math.min(hoverSteps.length - 1, Math.floor((Math.abs(hoverX - HALF) / HALF) * hoverSteps.length))];
  const hover = hoverX != null && hoverStep ? { x: hoverX, text: depthReadout(hoverSide, hoverStep) } : null;

  const edge = (side: BookSide) => {
    const t = total(side);
    return (
      <div className={`l2-depth__edge l2-depth__edge--${side}`} data-testid={`l2-depth-total-${side}`}>
        {t ? (
          <>
            <span className="l2-depth__num">{markWhole(t.shares)}</span>
            <span className="l2-depth__num">{depthDollars(t.dollars)}</span>
            <span className="l2-depth__word">{L2_DEPTH_CHART_LABELS[side]}</span>
          </>
        ) : null}
      </div>
    );
  };

  return (
    <div className="l2-depth" data-testid="l2-depth-chart">
      <div className="l2-depth__totals">
        {edge('bid')}
        {edge('ask')}
      </div>
      <div className="l2-depth__plot" onMouseMove={onMove} onMouseLeave={() => setHoverX(null)}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={L2_DEPTH_CHART_LABELS.aria}>
          <path className="l2-depth__area l2-depth__area--bid" d={area(sides.bid, -1, y)} />
          <path className="l2-depth__area l2-depth__area--ask" d={area(sides.ask, 1, y)} />
          <line className="l2-depth__mid" x1={HALF} x2={HALF} y1={0} y2={100} />
          {walls.map((w) => (
            <line key={w.id} className="l2-depth__wall" x1={w.x} x2={w.x} y1={w.from} y2={w.to} />
          ))}
          {hover && <line className="l2-depth__cursor" x1={hover.x} x2={hover.x} y1={0} y2={100} />}
        </svg>
        {walls.map((w) => (
          <span
            key={w.id}
            className={`l2-depth__walltag l2-depth__walltag--${w.side}`}
            data-testid="l2-depth-wall"
            style={tagPlace(w.side, w.x, w.to)}
          >
            {w.text}
          </span>
        ))}
      </div>
      <div className="l2-depth__axis">
        <span>{total('bid') ? markPrice(total('bid').price) : ''}</span>
        <span>
          {sides.bid[0] ? markPrice(sides.bid[0].price) : ''} | {sides.ask[0] ? markPrice(sides.ask[0].price) : ''}
        </span>
        <span>{total('ask') ? markPrice(total('ask').price) : ''}</span>
      </div>
      <div className="l2-depth__read" data-testid="l2-depth-read">{hover?.text ?? hint}</div>
    </div>
  );
}
