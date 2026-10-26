/**
 * A tile's compact 1-minute chart (approved mockup v1, 2026-10-26): candles, volume, the desk's
 * session VWAP and a last-price tag, in an SVG sized to the tile.
 */
import { memo, useLayoutEffect, useRef, useState } from 'react';
import { TOP_NINE_NO_BARS } from './topNineConstants';
import { topNineChartGeometry, type ChartBox } from './topNineChartGeometry';
import { useTopNineBars } from './useTopNineBars';

export const TopNineChart = memo(function TopNineChart(
  { symbol, lastPrice, endTime }: { symbol: string; lastPrice: number | null; endTime: number | null },
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<ChartBox>({ width: 0, height: 0 });
  const { bars, vwap, error, loaded } = useTopNineBars(symbol);

  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return undefined;
    const measure = () => setBox({ width: Math.floor(el.clientWidth), height: Math.floor(el.clientHeight) });
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = topNineChartGeometry(bars, vwap, lastPrice, box, endTime);
  return (
    <div className="top-nine-chart" ref={hostRef} data-testid={`top-nine-chart-${symbol}`}>
      {geo ? (
        <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`} aria-hidden="true">
          {geo.priceTicks.map((t) => (
            <g key={`p${t.label}`}>
              <line className="top-nine-chart__grid" x1={6} x2={geo.plotRight} y1={t.y} y2={t.y} />
              <text className="top-nine-chart__axis" x={geo.plotRight + 6} y={t.y + 4}>{t.label}</text>
            </g>
          ))}
          {geo.timeTicks.map((t) => (
            <g key={`t${t.label}`}>
              <line className="top-nine-chart__grid" x1={t.x} x2={t.x} y1={8} y2={geo.volBottom} />
              <text className="top-nine-chart__axis" x={t.x} y={box.height - 4} textAnchor="middle">{t.label}</text>
            </g>
          ))}
          {geo.candles.map((c) => (
            <g key={c.x} className={c.up ? 'is-up' : 'is-down'}>
              <rect className="top-nine-chart__vol" x={c.x - geo.bodyW / 2} y={c.volY} width={geo.bodyW} height={c.volH} />
              <line className="top-nine-chart__wick" x1={c.x} x2={c.x} y1={c.wickTop} y2={c.wickBottom} />
              <rect className="top-nine-chart__body" x={c.x - geo.bodyW / 2} y={c.bodyY} width={geo.bodyW} height={c.bodyH} />
            </g>
          ))}
          {geo.vwap.map((points, i) => (
            <polyline key={i} className="top-nine-chart__vwap" points={points} />
          ))}
          {geo.last && (
            <g className={geo.last.up ? 'is-up' : 'is-down'}>
              <line className="top-nine-chart__last" x1={6} x2={geo.plotRight} y1={geo.last.y} y2={geo.last.y} />
              <rect className="top-nine-chart__tag" x={geo.plotRight + 1} y={geo.last.y - 9} width={50} height={18} rx={3} />
              <text className="top-nine-chart__tag-text" x={geo.plotRight + 6} y={geo.last.y + 4}>{geo.last.label}</text>
            </g>
          )}
        </svg>
      ) : bars.length ? null : (
        <span className="top-nine-chart__empty" role="status">
          {error ? `1-minute bars did not load: ${error}` : loaded ? TOP_NINE_NO_BARS : 'Loading 1-minute bars…'}
        </span>
      )}
    </div>
  );
});
