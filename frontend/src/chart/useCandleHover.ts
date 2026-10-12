/**
 * Which candle the operator is reading (operator ask, 2026-10-12). The card opens once the pointer has rested
 * on one candle -- between its high and its low, give or take a few pixels -- for `CANDLE_HOVER_DWELL_MS`, so
 * a sweep across the chart never opens it. Once open it follows the pointer from candle to candle at once.
 * It closes when the pointer leaves the chart, a button goes down (a click, a pan, a drawing), or the pointer
 * reaches a drawing that tells its own story at a point (a label, a ring, a trend line, a level's tick).
 * A setup's box covers candles, so over its area the candle wins (operator report 2026-10-12, `hoverTarget.ts`):
 * the card opens on a candle in the box as it does anywhere, and the box's own card steps aside while it is
 * open. In a box the open card follows the pointer only while it stays on a candle; off them it closes and the
 * box's story shows again.
 */
import { useEffect, useState, type RefObject } from 'react';
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts';
import { CANDLE_HOVER_DWELL_MS, CANDLE_HOVER_HIT_SLACK_PX } from './candleHoverConstants';
import { hoverTarget, setCandleCardOpen } from './hoverTarget';

export interface CandleHover {
  /** The candle's place on the time scale, for reading it again from the series. */
  logical: number;
  time: Time;
  /** The pointer, in the pane's pixels, and the pane's size when it got there. */
  x: number;
  y: number;
  width: number;
  height: number;
}

interface PointerCandle {
  high: number;
  low: number;
}

function candleIn(data: unknown): PointerCandle | null {
  if (!data || typeof data !== 'object' || !('high' in data) || !('low' in data)) return null;
  const { high, low } = data as PointerCandle;
  return Number.isFinite(high) && Number.isFinite(low) ? { high, low } : null;
}

export function useCandleHover(
  chart: IChartApi | null,
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>,
  containerRef: RefObject<HTMLElement | null>,
): CandleHover | null {
  const [hover, setHover] = useState<CandleHover | null>(null);

  useEffect(() => {
    if (!chart) return;
    const box = containerRef.current;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let pending: CandleHover | null = null;
    let open = false;
    let pressed = false;

    const close = () => {
      if (timer != null) clearTimeout(timer);
      timer = null;
      pending = null;
      open = false;
      setCandleCardOpen(chart, false);
      setHover(null);
    };

    const onMove = (p: MouseEventParams<Time>) => {
      const series = candleSeriesRef.current;
      const point = p.point;
      const drawing = hoverTarget(p.hoveredObjectId);
      if (pressed || !series || !point || p.time == null || p.logical == null || (drawing && !drawing.area)) {
        close();
        return;
      }
      const candle = candleIn(p.seriesData.get(series));
      if (!candle) {
        close();
        return;
      }
      const next: CandleHover = {
        logical: p.logical,
        time: p.time,
        x: point.x,
        y: point.y,
        width: box?.clientWidth ?? 0,
        height: box?.clientHeight ?? 0,
      };
      const top = series.priceToCoordinate(candle.high);
      const bottom = series.priceToCoordinate(candle.low);
      const onCandle = top != null && bottom != null
        && point.y >= top - CANDLE_HOVER_HIT_SLACK_PX && point.y <= bottom + CANDLE_HOVER_HIT_SLACK_PX;
      if (open && (onCandle || !drawing)) {
        setHover(next);
        return;
      }
      if (!onCandle) {
        close();
        return;
      }
      const sameCandle = pending?.logical === next.logical;
      pending = next;
      if (sameCandle && timer != null) return;
      if (timer != null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        if (!pending) return;
        open = true;
        setCandleCardOpen(chart, true);
        setHover(pending);
      }, CANDLE_HOVER_DWELL_MS);
    };

    const onDown = () => {
      pressed = true;
      close();
    };
    const onUp = () => {
      pressed = false;
    };

    chart.subscribeCrosshairMove(onMove);
    box?.addEventListener('pointerdown', onDown, true);
    box?.addEventListener('pointerleave', close);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      try {
        chart.unsubscribeCrosshairMove(onMove);
      } catch {
        // maintainer: allow-swallow the chart was already disposed, so it holds no subscription
      }
      box?.removeEventListener('pointerdown', onDown, true);
      box?.removeEventListener('pointerleave', close);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      close();
    };
  }, [chart, candleSeriesRef, containerRef]);

  return hover;
}
