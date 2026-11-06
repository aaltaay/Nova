/**
 * Claude's orders on the Trader's charts (ADR 068, the approved design's 3 -- operator: "i do like these lines you
 * got on the chart"): on the 10-second, 1-minute and 5-minute panes of the stock Claude trades, each working order
 * and each armed break is a violet price line with its price on the axis (the stop solid red-violet), named at the
 * pane's left: "Claude · buy 510 on a print at 4.39 (up to 4.41)", "Claude · sell 250 at 4.49", "Claude · stop 510
 * at 4.12". Lines come and go with the seat's status; nothing here places or moves an order.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { IPriceLine, ISeriesApi } from 'lightweight-charts';
import type { ChartPaneOverlayProps } from '../chart';
import { useClaudeSeat } from './claudeSeatStore';
import { claudeChartLines, type ClaudeChartLine } from './claudeSeatWords';
import './claudeSeat.css';

const PANES = new Set(['10Sec', '1Min', '5Min']);
const COLOR: Record<ClaudeChartLine['kind'], string> = { buy: '#9d8cff', sell: '#9d8cff', stop: '#ff6b5f' };
const DASHED = 2;
const SOLID = 0;

function usePriceLines(series: ISeriesApi<'Candlestick'> | null, lines: ClaudeChartLine[]): void {
  const made = useRef(new Map<string, IPriceLine>());
  const key = JSON.stringify(lines);
  useEffect(() => {
    const map = made.current;
    if (!series) return undefined;
    const want = new Map(lines.map(l => [l.id, l]));
    for (const [id, pl] of map) {
      if (!want.has(id)) {
        try { series.removePriceLine(pl); } catch { /* the series went with its chart */ }
        map.delete(id);
      }
    }
    for (const l of lines) {
      const opts = {
        price: l.price, color: COLOR[l.kind], lineWidth: 1 as const,
        lineStyle: l.kind === 'stop' ? SOLID : DASHED, axisLabelVisible: true, title: '',
      };
      const have = map.get(l.id);
      if (have) have.applyOptions(opts);
      else map.set(l.id, series.createPriceLine(opts));
    }
    return undefined;
    // `key` carries `lines`: a new array with the same lines must not redraw them.
  }, [series, key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => {
    const map = made.current;
    if (series) for (const pl of map.values()) { try { series.removePriceLine(pl); } catch { /* gone */ } }
    map.clear();
  }, [series]);
}

const WORD_PX = 15;

/** A word whose price is off the pane's scale stays at its edge with an arrow (the design's "4.93 ↑"). */
export function pinned(y: number, height: number): { top: number; arrow: string } {
  if (y < WORD_PX) return { top: WORD_PX, arrow: y < 0 ? '↑ ' : '' };
  if (height > 0 && y > height - 4) return { top: height - 4, arrow: '↓ ' };
  return { top: y, arrow: '' };
}

/** Words top to bottom, each at least a word's height under the one above (two prices close together, or pinned). */
export function spread<T extends { top: number }>(words: T[]): T[] {
  const out = [...words].sort((a, b) => a.top - b.top);
  for (let i = 1; i < out.length; i += 1) {
    if (out[i].top < out[i - 1].top + WORD_PX) out[i] = { ...out[i], top: out[i - 1].top + WORD_PX };
  }
  return out;
}

export function ClaudeSeatChartLayer(props: ChartPaneOverlayProps) {
  const { status } = useClaudeSeat();
  const onPane = PANES.has(props.timeframe);
  const lines = useMemo(
    () => (onPane ? claudeChartLines(status, props.symbol) : []),
    [onPane, status, props.symbol],
  );
  const series = props.candleSeriesRef.current;
  usePriceLines(series, lines);
  const [ys, setYs] = useState<Record<string, number | null>>({});

  useEffect(() => {
    if (!series || !lines.length) { setYs({}); return undefined; }
    let frame = 0;
    const place = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next: Record<string, number | null> = {};
        for (const l of lines) next[l.id] = series.priceToCoordinate(l.price);
        setYs(next);
      });
    };
    place();
    const ts = props.chart?.timeScale();
    ts?.subscribeVisibleLogicalRangeChange(place);
    const body = props.containerRef.current;
    const ro = body && typeof ResizeObserver !== 'undefined' ? new ResizeObserver(place) : null;
    if (body) ro?.observe(body);
    return () => {
      cancelAnimationFrame(frame);
      ts?.unsubscribeVisibleLogicalRangeChange(place);
      ro?.disconnect();
    };
  }, [series, lines, props.chart, props.containerRef, props.barsRevision]);

  if (!lines.length) return null;
  const height = props.containerRef.current?.clientHeight ?? 0;
  const words = spread(lines.flatMap(l => {
    const y = ys[l.id];
    return y == null ? [] : [{ line: l, ...pinned(y, height) }];
  }));
  return (
    <div className="claude-chart-words" data-testid="claude-chart-words" aria-hidden="true">
      {words.map(({ line: l, top, arrow }) => (
        <span key={l.id} className={`claude-chart-word claude-chart-word--${l.kind}`} style={{ top }}>
          {arrow}{l.label}
        </span>
      ))}
    </div>
  );
}
