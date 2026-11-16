/**
 * One Top 9 tile's 1-minute chart, at phone size. The bars, the session VWAP, the geometry and the
 * LULD band are the desk tile's own (`useTopNineBars`, `topNineChartGeometry`, `topNineLuldShape`);
 * only the margins differ: a tile this small keeps no price axis and no time row, and lays its
 * last-price tag over the plot's right edge.
 */
import { memo, useLayoutEffect, useRef, useState } from 'react';
import { TOP_NINE_LULD_NONE, TOP_NINE_NO_BARS } from '../../top_nine/topNineConstants';
import { topNineChartGeometry, type ChartBox, type ChartInsets } from '../../top_nine/topNineChartGeometry';
import { topNineLuldShape } from '../../top_nine/topNineLuld';
import { useTopNineBars } from '../../top_nine/useTopNineBars';
import { useTopNineLuld } from '../../top_nine/useTopNineLuld';

/**
 * No time row, a short volume strip, and a gutter just wide enough for the last-price tag, so the tag
 * never covers the newest candles. Thirty minutes where the pop-up shows ninety: ninety candles in a
 * tile this wide would be under a pixel each.
 */
export const PHONE_TILE_INSETS: ChartInsets = {
  axisW: 34, left: 2, top: 5, timeH: 0, volH: 16, minW: 60, minH: 44, minutes: 30,
};

export const TopNineTileChart = memo(function TopNineTileChart(
  { symbol, lastPrice, endTime, luld: luldOn }: {
    symbol: string; lastPrice: number | null; endTime: number | null; luld: boolean;
  },
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<ChartBox>({ width: 0, height: 0 });
  const { bars, vwap, error, loaded } = useTopNineBars(symbol);
  const trail = useTopNineLuld(symbol, luldOn);

  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return undefined;
    const measure = () => setBox({ width: Math.floor(el.clientWidth), height: Math.floor(el.clientHeight) });
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const geo = topNineChartGeometry(bars, vwap, lastPrice, box, endTime, PHONE_TILE_INSETS);
  const luld = geo ? topNineLuldShape(trail, geo.scale, geo.last?.y ?? null) : null;
  return (
    <div className="ph-t9chart" ref={hostRef} data-testid={`phone-top9-chart-${symbol}`}>
      {geo ? (
        <>
          <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`} aria-hidden="true">
            <line className="ph-t9chart__base" x1={0} x2={box.width} y1={geo.volTop - 3} y2={geo.volTop - 3} />
            {geo.candles.map((c) => (
              <g key={c.x} className={c.up ? 'is-up' : 'is-down'}>
                <rect className="ph-t9chart__vol" x={c.x - geo.bodyW / 2} y={c.volY} width={geo.bodyW} height={c.volH} />
                <line className="ph-t9chart__wick" x1={c.x} x2={c.x} y1={c.wickTop} y2={c.wickBottom} />
                <rect className="ph-t9chart__body" x={c.x - geo.bodyW / 2} y={c.bodyY} width={geo.bodyW} height={c.bodyH} />
              </g>
            ))}
            {geo.vwap.map((points, i) => (
              <polyline key={i} className="ph-t9chart__vwap" points={points} />
            ))}
            {luld?.pieces.map((p, i) => (
              <line
                key={`l${i}`}
                className={`ph-t9chart__luld${p.dashed ? ' is-approx' : ''}`}
                x1={p.x1}
                x2={p.x2}
                y1={p.y1}
                y2={p.y2}
              />
            ))}
            {geo.last ? (
              <line
                className={`ph-t9chart__last ${geo.last.up ? 'is-up' : 'is-down'}`}
                x1={0}
                x2={geo.plotRight}
                y1={geo.last.y}
                y2={geo.last.y}
              />
            ) : null}
          </svg>
          {geo.last ? (
            <span
              className={`ph-t9chart__tag ${geo.last.up ? 'is-up' : 'is-down'}`}
              style={{ top: Math.max(0, Math.min(box.height - 14, geo.last.y - 7)) }}
            >
              {geo.last.label}
            </span>
          ) : null}
          {/* A tile this small has room for the short form only; the pop-up's tile spells the reason out. */}
          {luld?.none ? <span className="ph-t9chart__none" title={luld.none.why}>{TOP_NINE_LULD_NONE}</span> : null}
        </>
      ) : bars.length ? null : (
        <span className="ph-t9chart__empty" role="status">
          {error ? 'Bars did not load' : loaded ? TOP_NINE_NO_BARS : 'Loading…'}
        </span>
      )}
    </div>
  );
});
