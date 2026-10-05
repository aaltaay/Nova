/**
 * How long until the forming candle closes, on the venue's clock (operator ask,
 * 2026-09-24): the wall clock on Live and Paper, the replay playhead on Sim.
 *
 * Buckets are `tradeBucket`'s -- Eastern wall time read as UTC seconds, floored
 * to the period -- so the countdown ends on the second the live tip opens its
 * next candle. It is stated only while a candle can form: a minute timeframe,
 * inside the 04:00-20:00 ET session on a weekday, and a chart whose newest bar
 * is from that Eastern day. The client does not know NYSE holidays, and a
 * holiday has no bar today, so the chart says nothing then rather than count
 * down a candle that will never print.
 */
import type { Time } from 'lightweight-charts';
import { etChartSeconds } from '../tickerChartData';
import type { PaneWordRect } from './paneWords';
import { etMinutesFromChartTime, sessionKindFromEtMinutes } from './sessionHighlight';
import {
  CHART_BAR_COUNTDOWN_BAR_SPACING_PX,
  CHART_BAR_COUNTDOWN_EDGE_PX,
  CHART_BAR_COUNTDOWN_GAP_PX,
  CHART_BAR_COUNTDOWN_HEIGHT_PX,
  CHART_BAR_COUNTDOWN_PAD_X_PX,
  CHART_BAR_COUNTDOWN_STACK_ROWS,
  CHART_BAR_COUNTDOWN_TIMEFRAME_RE,
  CHART_BAR_COUNTDOWN_WARN_SEC,
  CHART_BAR_COUNTDOWN_WORD_GAP_PX,
} from './barCountdownConstants';

const DAY_SEC = 86_400;

export interface BarCountdownBar {
  time: Time;
  high: number;
  low: number;
  close: number;
}

export interface BarCountdown {
  /** Seconds until the forming candle closes, 1..period: at the boundary the next candle starts at a full period. */
  remainingSec: number;
  text: string;
  /** Inside the last `CHART_BAR_COUNTDOWN_WARN_SEC` seconds. */
  warn: boolean;
  /**
   * `tip`: the newest bar is the forming candle. `next`: nothing has printed in
   * this period yet, so the candle will form in the slot after the newest bar.
   */
  anchor: 'tip' | 'next';
}

/** The candle period in seconds for a minute timeframe, else null (no countdown). */
export function barCountdownPeriodSec(timeframe: string): number | null {
  const match = CHART_BAR_COUNTDOWN_TIMEFRAME_RE.exec(timeframe);
  const minutes = match ? Number(match[1]) : Number.NaN;
  return Number.isInteger(minutes) && minutes > 0 ? minutes * 60 : null;
}

/** `00:42`, `04:17`; `1:02:03` past an hour. */
export function formatBarCountdown(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const h = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function inSession(chartSec: number): boolean {
  const weekday = new Date(chartSec * 1000).getUTCDay();
  if (weekday === 0 || weekday === 6) return false;
  const minutes = etMinutesFromChartTime(chartSec as Time);
  return minutes !== null && sessionKindFromEtMinutes(minutes) !== 'closed';
}

/**
 * The countdown at `nowMs` (epoch ms on the venue's clock) for a chart whose
 * newest bar is `lastBar`, or null when no candle is forming.
 */
export function barCountdown(
  nowMs: number | null,
  timeframe: string,
  lastBar: BarCountdownBar | null,
): BarCountdown | null {
  const period = barCountdownPeriodSec(timeframe);
  if (period === null || nowMs === null || !Number.isFinite(nowMs)) return null;
  if (!lastBar || typeof lastBar.time !== 'number') return null;
  const now = etChartSeconds(nowMs);
  if (!inSession(now)) return null;
  if (Math.floor(lastBar.time / DAY_SEC) !== Math.floor(now / DAY_SEC)) return null;
  const bucket = Math.floor(now / period) * period;
  // A bar more than one period ahead of the clock means the clock is wrong,
  // not that a candle is forming; one period ahead is a print that beat the
  // clock across the boundary.
  if (lastBar.time > bucket + period) return null;
  const forming = Math.max(bucket, lastBar.time);
  const remainingSec = Math.min(period, forming + period - now);
  return {
    remainingSec,
    text: formatBarCountdown(remainingSec),
    warn: remainingSec <= CHART_BAR_COUNTDOWN_WARN_SEC,
    anchor: lastBar.time >= bucket ? 'tip' : 'next',
  };
}

export interface BarCountdownChipBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Whether the chip, grown by the gap kept between words, touches `word`. */
function touchesWord(box: BarCountdownChipBox, word: PaneWordRect): boolean {
  const gap = CHART_BAR_COUNTDOWN_WORD_GAP_PX;
  return box.x < word.right + gap && box.x + box.width + gap > word.left
    && box.y < word.bottom + gap && box.y + box.height + gap > word.top;
}

/**
 * Where the chip sits, in media pixels: centred over the forming candle, just
 * above its wick; below it when the top of the pane leaves no room. Null when
 * the candle's slot is scrolled out of the pane -- pinning the chip to an edge
 * would put it over some other candle.
 *
 * It never covers a word (`words`: the labels, pins and tags the pane's other
 * primitives drew). When the usual spot touches one it tries, in this order,
 * beside the candle on its right (at the wick's middle, then over it), under
 * the candle, beside it on its left, and then higher or lower in a stack
 * above and below the wick; the first spot clear of every word wins. A spot
 * is kept clear of the forming candle itself, and with no clear spot at all
 * the chip is not drawn -- the countdown is a convenience, a covered label is
 * information lost.
 */
export function barCountdownChipBox(args: {
  anchorX: number | null;
  wickTopY: number | null;
  wickBottomY: number | null;
  textWidth: number;
  paneWidth: number;
  paneHeight: number;
  /** The pane's candle spacing, for the spots beside the candle. */
  barSpacing?: number;
  words?: readonly PaneWordRect[];
}): BarCountdownChipBox | null {
  const { anchorX, wickTopY, wickBottomY, textWidth, paneWidth, paneHeight, words = [] } = args;
  if (anchorX === null || wickTopY === null || wickBottomY === null) return null;
  if (anchorX < 0 || anchorX > paneWidth) return null;
  const width = Math.ceil(textWidth) + CHART_BAR_COUNTDOWN_PAD_X_PX * 2;
  const height = CHART_BAR_COUNTDOWN_HEIGHT_PX;
  const edge = CHART_BAR_COUNTDOWN_EDGE_PX;
  const maxX = Math.max(edge, paneWidth - width - edge);
  const maxY = Math.max(edge, paneHeight - height - edge);
  const x = Math.min(Math.max(anchorX - width / 2, edge), maxX);
  let y = wickTopY - CHART_BAR_COUNTDOWN_GAP_PX - height;
  if (y < edge) {
    const below = wickBottomY + CHART_BAR_COUNTDOWN_GAP_PX;
    y = below <= maxY ? below : edge;
  }
  const usual: BarCountdownChipBox = { x, y: Math.min(Math.max(y, edge), maxY), width, height };
  if (!words.some(w => touchesWord(usual, w))) return usual;

  const half = (args.barSpacing ?? CHART_BAR_COUNTDOWN_BAR_SPACING_PX) / 2;
  const gap = CHART_BAR_COUNTDOWN_GAP_PX;
  const aboveY = wickTopY - gap - height;
  const belowY = wickBottomY + gap;
  const midY = (wickTopY + wickBottomY) / 2 - height / 2;
  const rightX = anchorX + half + gap;
  const leftX = anchorX - half - gap - width;
  const step = height + CHART_BAR_COUNTDOWN_WORD_GAP_PX;
  const candidates: [number, number][] = [
    [rightX, midY], [rightX, aboveY], [x, belowY], [rightX, belowY], [leftX, midY], [leftX, aboveY], [leftX, belowY],
  ];
  for (let k = 1; k <= CHART_BAR_COUNTDOWN_STACK_ROWS; k += 1) {
    candidates.push([x, aboveY - k * step], [x, belowY + k * step]);
  }
  const candle = { left: anchorX - half, right: anchorX + half, top: wickTopY, bottom: wickBottomY };
  for (const [cx, cy] of candidates) {
    // Beside the candle means in the room next to it, not pushed back over it by the pane's edge.
    if (cx < edge || cx > maxX || cy < edge || cy > maxY) continue;
    const box = { x: cx, y: cy, width, height };
    const onCandle = box.x < candle.right && box.x + width > candle.left && box.y < candle.bottom
      && box.y + height > candle.top;
    if (!onCandle && !words.some(w => touchesWord(box, w))) return box;
  }
  return null;
}
