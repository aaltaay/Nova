/**
 * The desk's Level 2 marks on the phone's book (ADR 070 amendment 2026-11-13, mockup v2 option C): a big seller or
 * buyer's block and its banner, a hidden seller or buyer, what was pulled, and the depth chart under the rows.
 *
 * Every mark is the book watcher's verdict, read with the desk ladder's own functions (`ibkr/bookWatch`,
 * `bookWatchHidden`, `bookWatchBig`) for the rows on screen and drawn in the phone's shape. Nothing here works out a
 * wall, a pull or a signal. The depth chart is the desk's `Level2DepthChart`; on the phone it is one button that
 * opens the read page (`#/book/SYM`).
 */
import type { ReactNode } from 'react';
import { Maximize2 } from 'lucide-react';
import { Level2DepthChart } from '../../ibkr/Level2DepthChart';
import { pulledHere, pullMarks, type BookSide, type BookWatchState, type PulledHere, type PullMark } from '../../ibkr/bookWatch';
import { bigBanner, bigRows, type BigBanner, type BigBannerPart, type BigRow } from '../../ibkr/bookWatchBig';
import { hiddenHere, hiddenMarks } from '../../ibkr/bookWatchHidden';
import type { DepthLevel } from '../../ibkr/types';
import { go } from '../phoneRoute';
import '../../ibkr/level2DepthChart.css';
import './bookMarks.css';

/** The depth chart's height under the rows: its totals, its plot and its price line. */
export const DEPTH_STRIP_PX = 50;

/** One side's marks for the rows on screen. */
export interface SideMarks {
  /** A big seller's or buyer's rows, by row index. */
  big: Map<number, BigRow>;
  /** Prices where a hidden seller or buyer holds (outlined), and where size was pulled and sits again. */
  hidden: Map<string, PulledHere>;
  pulled: Map<string, PulledHere>;
  /** The marks between rows: hidden first at a place, then what left. */
  marks: PullMark[];
  banner: BigBanner | null;
}

const NONE: SideMarks = { big: new Map(), hidden: new Map(), pulled: new Map(), marks: [], banner: null };

/** The desk ladder's reading of one side (`DepthLadder` `MontageSide`), for the rows the phone shows. */
export function sideMarks(watch: BookWatchState | null, side: BookSide, rows: readonly DepthLevel[], nowMs: number): SideMarks {
  if (!watch || !rows.length) return { ...NONE, banner: watch ? bigBanner(watch, side, nowMs) : null };
  return {
    big: bigRows(watch, side, rows, nowMs),
    hidden: hiddenHere(watch, side, rows, nowMs),
    pulled: pulledHere(watch, side, rows, nowMs),
    marks: [...hiddenMarks(watch, side, rows, nowMs), ...pullMarks(watch, side, rows, nowMs)],
    banner: bigBanner(watch, side, nowMs),
  };
}

/**
 * The banner's words that fit a 116 px column: who, the price, the size and how it ended. The float and the pace
 * are on the read page; the desk's narrow rail drops them the same way (`bookWatchBig` `BigBannerPart`).
 */
export function bannerWords(banner: BigBanner): string {
  const keep = new Set<BigBannerPart['key']>(['lead', 'price', 'size', 'verdict']);
  return banner.parts.filter((p) => keep.has(p.key)).map((p) => `${p.sep}${p.text}`).join('');
}

/** The banner over a side's column head, taking no height. */
export function BigBannerChip({ banner, side }: { banner: BigBanner | null; side: BookSide }) {
  if (!banner) return null;
  return (
    <p className="ph-marks__banner" data-side={side} data-kind={banner.light ? 'light' : banner.kind} style={{ opacity: banner.opacity }} role="status" data-testid={`phone-big-${side}`}>
      <b>{bannerWords(banner)}</b>
    </p>
  );
}

/** Inside a big seller's row: the tag on its first row, and the bar of what traded there on its last. */
export function BigRowParts({ row }: { row: BigRow | undefined }) {
  if (!row) return null;
  return (
    <>
      {row.tag ? <span className={`ph-marks__bigtag${row.light ? ' is-light' : ''}`} data-testid="phone-big-tag">{row.tag}</span> : null}
      {row.takenPct !== null ? <span className="ph-marks__bigbar" aria-hidden="true"><span style={{ width: `${row.takenPct}%` }} /></span> : null}
    </>
  );
}

/** The class a row's half takes from its marks: a big block's edges, a hidden price's outline, a pulled price. */
export function rowMarkClass(big: BigRow | undefined, hidden: boolean, pulled: boolean): string {
  return [
    big?.light ? 'is-biglight' : '',
    big && !big.light ? 'is-big' : '',
    big && !big.light && big.first ? 'is-big-first' : '',
    big && !big.light && big.last ? 'is-big-last' : '',
    hidden ? 'is-hidden' : '',
    pulled ? 'is-pulled' : '',
  ].filter(Boolean).join(' ');
}

/** The marks between rows, over one side's half of the rows box; `before` is the row a mark sits on top of. */
export function MarksLayer({ marks, side, rowPx, rows }: { marks: readonly PullMark[]; side: BookSide; rowPx: number; rows: number }) {
  if (!marks.length) return null;
  const at = new Map<number, PullMark[]>();
  for (const m of marks) {
    const place = Math.min(m.before, rows);
    at.set(place, [...(at.get(place) ?? []), m]);
  }
  const out: ReactNode[] = [];
  for (const [before, here] of at) {
    const lead = here.find((m) => m.kind === 'approach') ?? here.find((m) => m.kind === 'pulled') ?? here[0];
    out.push(
      <div
        key={`${side}-${before}`}
        className="ph-marks__line"
        data-side={side}
        data-kind={lead.kind}
        data-edge={before === 0 ? 'head' : before >= rows ? 'end' : 'edge'}
        style={{ top: before * rowPx, opacity: Math.max(...here.map((m) => m.opacity)) }}
      >
        {here.map((m) => (
          <i key={m.id} data-kind={m.kind} data-testid={`phone-mark-${m.kind}`}>{m.label}</i>
        ))}
      </div>,
    );
  }
  return <>{out}</>;
}

/** The depth chart under the rows: the desk's chart, and one button over it that opens the read page. */
export function DepthStrip({ symbol, bids, asks, watch }: {
  symbol: string;
  bids: readonly DepthLevel[];
  asks: readonly DepthLevel[];
  watch: BookWatchState | null;
}) {
  return (
    <div className="ph-depth" style={{ height: DEPTH_STRIP_PX }} data-testid="phone-depth">
      <Level2DepthChart bids={[...bids]} asks={[...asks]} watch={watch} alwaysOn />
      <span className="ph-depth__open" aria-hidden="true"><Maximize2 size={9} /></span>
      <button
        type="button"
        className="ph-depth__btn"
        aria-label={`Open ${symbol}'s Level 2 read: the depth chart large and every mark`}
        data-testid="phone-depth-open"
        onClick={() => go({ screen: 'book', symbol })}
      />
    </div>
  );
}
