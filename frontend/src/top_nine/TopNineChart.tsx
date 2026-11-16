/**
 * A tile's compact 1-minute chart (approved mockup v1, 2026-10-26): candles, volume, the desk's
 * session VWAP and a last-price tag, in an SVG sized to the tile, with Nova's LULD band over it
 * (approved mockup, 2026-10-27; topNineLuld) or the words that say why there is none. `luld` false
 * (a list with no band, TOP_NINE_LULD_LISTS) draws and asks for neither.
 */
import { memo, useLayoutEffect, useRef, useState } from 'react';
import { TOP_NINE_NO_BARS } from './topNineConstants';
import { topNineChartGeometry, type ChartBox } from './topNineChartGeometry';
import { topNineLuldShape } from './topNineLuld';
import { useTopNineBars } from './useTopNineBars';
import { useTopNineLuld } from './useTopNineLuld';

const TAG_W = 52;
const TICK_CLEAR = 15;

export const TopNineChart = memo(function TopNineChart(
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
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = topNineChartGeometry(bars, vwap, lastPrice, box, endTime);
  const luld = geo ? topNineLuldShape(trail, geo.scale, geo.last?.y ?? null) : null;
  const tagYs = luld?.tags.map((t) => t.y) ?? [];
  const ticks = geo?.priceTicks.filter((t) => tagYs.every((y) => Math.abs(t.y - y) > TICK_CLEAR)) ?? [];
  return (
    <div className="top-nine-chart" ref={hostRef} data-testid={`top-nine-chart-${symbol}`}>
      {geo ? (
        <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`} aria-hidden="true">
          {ticks.map((t) => (
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
          {luld?.pieces.map((p, i) => (
            <line
              key={`l${i}`}
              className={`top-nine-chart__luld${p.dashed ? ' is-approx' : ''}`}
              x1={p.x1}
              x2={p.x2}
              y1={p.y1}
              y2={p.y2}
            />
          ))}
          {geo.last && (
            <g className={geo.last.up ? 'is-up' : 'is-down'}>
              <line className="top-nine-chart__last" x1={6} x2={geo.plotRight} y1={geo.last.y} y2={geo.last.y} />
              <rect className="top-nine-chart__tag" x={geo.plotRight + 1} y={geo.last.y - 9} width={50} height={18} rx={3} />
              <text className="top-nine-chart__tag-text" x={geo.plotRight + 6} y={geo.last.y + 4}>{geo.last.label}</text>
            </g>
          )}
          {luld?.tags.map((t) => (
            <g key={t.side} className="top-nine-chart__luld-tag" data-testid={`top-nine-luld-${t.side}-${symbol}`}>
              <rect x={geo.plotRight + 1} y={t.y - 9} width={TAG_W} height={18} rx={3} />
              <text x={geo.plotRight + 4} y={t.y + 4}>{t.label}</text>
            </g>
          ))}
          {luld?.none ? (
            <text
              className="top-nine-chart__luld-none"
              x={geo.plotRight - 4}
              y={20}
              textAnchor="end"
              data-testid={`top-nine-luld-none-${symbol}`}
            >
              <title>{luld.none.why}</title>
              {luld.none.text}
            </text>
          ) : null}
        </svg>
      ) : bars.length ? null : (
        <span className="top-nine-chart__empty" role="status">
          {error ? `1-minute bars did not load: ${error}` : loaded ? TOP_NINE_NO_BARS : 'Loading 1-minute bars…'}
        </span>
      )}
    </div>
  );
});
