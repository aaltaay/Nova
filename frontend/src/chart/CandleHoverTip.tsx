/**
 * The candle's hover card (operator ask, 2026-10-12): rest the pointer on a candle and a card beside it names
 * the candle -- its time and session, its move open to close, open / high / low / close, its range, where it
 * closed in that range and its wicks, its volume against the candles before it, and where it closed against
 * the prior close, the session VWAP and the 9:30 open. Every figure comes from `candleHoverStats.ts`; a row
 * whose source is missing is left out. The card takes no pointer events, so the chart keeps every gesture,
 * and the candle's column is shaded while it is open.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { MismatchDirection, type IChartApi, type ISeriesApi, type Logical } from 'lightweight-charts';
import type { IndicatorBar } from '../chartIndicators';
import { tickerReady, type TickerStreamState } from '../hooks/tickerStore';
import { useTickerSelect } from '../hooks/useTickerStream';
import { isDailyTimeframe, isSubMinuteTimeframe, timeframeSeconds } from '../tickerChartData';
import { fmtPct, fmtPrice, fmtVolume } from '../utils/quoteFormat';
import {
  CANDLE_HOVER_CARD_GAP_PX,
  CANDLE_HOVER_CARD_W_PX,
  CANDLE_HOVER_EDGE_PX,
  CANDLE_HOVER_REFRESH_MS,
  CANDLE_HOVER_VOLUME_LOOKBACK,
  CANDLE_HOVER_VOLUME_METER_MAX,
  CANDLE_HOVER_VOLUME_SCAN_LIMIT,
} from './candleHoverConstants';
import {
  candleClockLabel,
  candleDayLabel,
  candleEpoch,
  candleSession,
  candleShape,
  closeInRangeLabel,
  dayVolumeThrough,
  dollarsTraded,
  regularOpenOf,
  timeframeLabel,
  volumeVsAverage,
  vwapAtClose,
  type CandleOhlc,
} from './candleHoverStats';
import { chartContextMenuPortalTarget } from './chartContextMenuPortal';
import { useCandleHover, type CandleHover } from './useCandleHover';
import { etDayKey, sessionVwapPoints, vwapSourceForPane } from './vwapSession';
import type { VwapSource } from './useVwapSourceBars';

interface CandleHoverTipProps {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: RefObject<ISeriesApi<'Histogram'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  symbol: string;
  timeframe: string;
  paneBars: IndicatorBar[];
  vwapSource: VwapSource;
}

function ohlcOf(data: unknown): CandleOhlc | null {
  if (!data || typeof data !== 'object' || !('open' in data)) return null;
  const { open, high, low, close } = data as CandleOhlc;
  return [open, high, low, close].every(Number.isFinite) ? { open, high, low, close } : null;
}

function valueOf(data: unknown): number | null {
  if (!data || typeof data !== 'object' || !('value' in data)) return null;
  const { value } = data as { value: number };
  return Number.isFinite(value) ? value : null;
}

/** The volumes of up to `CANDLE_HOVER_VOLUME_LOOKBACK` candles before `logical`, newest first. */
function priorVolumes(vol: ISeriesApi<'Histogram'>, logical: number): number[] {
  const out: number[] = [];
  for (let k = 1; k <= CANDLE_HOVER_VOLUME_SCAN_LIMIT && out.length < CANDLE_HOVER_VOLUME_LOOKBACK; k += 1) {
    if (logical - k < 0) break;
    const v = valueOf(vol.dataByIndex(logical - k, MismatchDirection.None));
    if (v != null) out.push(v);
  }
  return out;
}

function priorCandleClose(series: ISeriesApi<'Candlestick'>, logical: number): number | null {
  for (let k = 1; k <= CANDLE_HOVER_VOLUME_SCAN_LIMIT && logical - k >= 0; k += 1) {
    const bar = ohlcOf(series.dataByIndex(logical - k, MismatchDirection.None));
    if (bar) return bar.close;
  }
  return null;
}

function newestDay(series: ISeriesApi<'Candlestick'>): number | null {
  const last = series.dataByIndex(Number.MAX_SAFE_INTEGER, MismatchDirection.NearestLeft);
  const epoch = last ? candleEpoch(last.time) : null;
  return epoch == null ? null : etDayKey(epoch);
}

/** Green for up, red for down, nothing when flat or unknown. */
function tone(value: number | null | undefined): string | undefined {
  if (value == null || !Number.isFinite(value) || value === 0) return undefined;
  return value > 0 ? 'candle-tip__up' : 'candle-tip__down';
}

function classes(...names: (string | undefined)[]): string {
  return names.filter(Boolean).join(' ');
}

/** A size as a percent, no sign: a range is never "+". */
function plainPct(fraction: number | null): string {
  return fraction == null || !Number.isFinite(fraction) ? '' : ` · ${(fraction * 100).toFixed(2)}%`;
}

function signedPrice(value: number): string {
  if (value === 0) return fmtPrice(0);
  return `${value > 0 ? '+' : '−'}${fmtPrice(Math.abs(value))}`;
}

interface Row {
  label: string;
  value: string;
  tone?: number | null;
}

function Rows({ rows }: { rows: Row[] }) {
  return (
    <>
      {rows.map(row => (
        <div key={row.label} className="candle-tip__row">
          <span>{row.label}</span>
          <span className={tone(row.tone)}>{row.value}</span>
        </div>
      ))}
    </>
  );
}

export function CandleHoverTip({
  chart, candleSeriesRef, volSeriesRef, containerRef, symbol, timeframe, paneBars, vwapSource,
}: CandleHoverTipProps) {
  const hover = useCandleHover(chart, candleSeriesRef, containerRef);
  const open = hover != null;

  // The forming candle keeps changing under a still pointer: read it again while the card is open.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!open) return;
    const id = setInterval(() => setTick(t => t + 1), CANDLE_HOVER_REFRESH_MS);
    return () => clearInterval(id);
  }, [open]);

  // The ticker's prior close (a Sim replay's own, #542); read only while the card is open.
  const selectPriorClose = useCallback(
    (state: TickerStreamState) => (tickerReady(state, symbol) ? state.detail?.snapshot?.prev_close ?? null : null),
    [symbol],
  );
  const tickerPriorClose = useTickerSelect(open ? symbol : null, selectPriorClose);

  const daily = isDailyTimeframe(timeframe);
  const source = useMemo(
    () => (open && !daily ? vwapSourceForPane(vwapSource.bars, paneBars, timeframe) : null),
    [open, daily, vwapSource.bars, paneBars, timeframe],
  );
  const vwapPoints = useMemo(() => (source ? sessionVwapPoints(source) : null), [source]);

  if (!hover || !chart) return null;
  const series = candleSeriesRef.current;
  const vol = volSeriesRef.current;
  if (!series) return null;
  const bar = ohlcOf(series.dataByIndex(hover.logical, MismatchDirection.None));
  const epoch = candleEpoch(hover.time);
  if (!bar || epoch == null) return null;

  const seconds = daily ? 0 : timeframeSeconds(timeframe);
  const end = epoch + seconds;
  const shape = candleShape(bar);
  const volume = vol ? valueOf(vol.dataByIndex(hover.logical, MismatchDirection.None)) : null;
  const vsAverage = vol ? volumeVsAverage(volume, priorVolumes(vol, hover.logical)) : null;
  const dollars = dollarsTraded(volume, bar);
  const dayVolume = source ? dayVolumeThrough(source, epoch, end) : null;
  const vwap = dayVolume && vwapPoints ? vwapAtClose(vwapPoints, epoch, end) : null;
  const rthOpen = source ? regularOpenOf(source, epoch) : null;
  // An intraday candle measures from the ticker's prior close only on the session that close belongs to.
  const priorClose = daily
    ? priorCandleClose(series, hover.logical)
    : newestDay(series) === etDayKey(epoch) ? tickerPriorClose : null;
  const session = daily ? null : candleSession(epoch);
  const changeFrom = (base: number | null) => (base != null && base > 0 ? (bar.close - base) / base : null);

  const shapeRows: Row[] = [
    { label: 'Range (low → high)', value: `${fmtPrice(shape.range)}${plainPct(shape.rangeFrac)}` },
  ];
  const inRange = closeInRangeLabel(shape.closeInRange);
  if (inRange) shapeRows.push({ label: 'Closed in the range', value: inRange });
  shapeRows.push({ label: 'Wicks (top · bottom)', value: `${fmtPrice(shape.upperWick)} · ${fmtPrice(shape.lowerWick)}` });

  const volumeRows: Row[] = [];
  if (vsAverage) {
    volumeRows.push({
      label: vsAverage.count === 1
        ? 'vs the candle before'
        : `vs last ${vsAverage.count} candles (avg ${fmtVolume(vsAverage.average)})`,
      value: `${vsAverage.multiple.toFixed(1)}×`,
      tone: vsAverage.multiple >= 1 ? 1 : null,
    });
  }
  if (dollars != null) volumeRows.push({ label: 'Dollars traded', value: `≈ $${fmtVolume(dollars)}` });
  if (dayVolume) {
    volumeRows.push({ label: `Day volume by this candle${dayVolume.fromOpen ? '' : ' (partial)'}`, value: fmtVolume(dayVolume.volume) });
  }

  const closedRows: Row[] = [];
  const fromPrior = changeFrom(priorClose);
  if (fromPrior != null) {
    const which = daily && timeframe !== '1Day' ? 'prior candle' : 'prior close';
    closedRows.push({ label: `vs ${which} ${fmtPrice(priorClose)}`, value: fmtPct(fromPrior), tone: fromPrior });
  }
  const fromVwap = changeFrom(vwap);
  if (fromVwap != null) {
    const partial = dayVolume?.fromOpen ? '' : ' (partial)';
    const side = fromVwap > 0 ? ' above' : fromVwap < 0 ? ' below' : '';
    closedRows.push({ label: `vs VWAP ${fmtPrice(vwap)}${partial}`, value: `${fmtPct(fromVwap)}${side}`, tone: fromVwap });
  }
  const fromOpen = changeFrom(rthOpen);
  if (fromOpen != null) closedRows.push({ label: `vs 9:30 open ${fmtPrice(rthOpen)}`, value: fmtPct(fromOpen), tone: fromOpen });

  const title = daily ? candleDayLabel(epoch) : candleClockLabel(epoch, seconds, isSubMinuteTimeframe(timeframe));
  const meter = vsAverage ? Math.min(1, vsAverage.multiple / CANDLE_HOVER_VOLUME_METER_MAX) : null;

  return (
    <>
      <CandleColumn chart={chart} hover={hover} />
      <CandleCard hover={hover} chart={chart} containerRef={containerRef}>
        <div className="candle-tip__top">
          <span>{title}</span>
          <span className="candle-tip__muted">{daily ? timeframeLabel(timeframe) : `${candleDayLabel(epoch)} · ${timeframeLabel(timeframe)}`}</span>
          {session && <span className={`candle-tip__chip candle-tip__chip--${session.kind}`}>{session.label}</span>}
        </div>
        <div className="candle-tip__hero">
          <span className={classes('candle-tip__pct', tone(shape.change))}>{fmtPct(shape.changeFrac, '—')}</span>
          <span className="candle-tip__muted">
            <span className={tone(shape.change)}>{signedPrice(shape.change)}</span> open → close
          </span>
        </div>
        <div className="candle-tip__ohlc">
          <div><span>Open</span><b>{fmtPrice(bar.open)}</b></div>
          <div><span>High</span><b>{fmtPrice(bar.high)}</b></div>
          <div><span>Low</span><b>{fmtPrice(bar.low)}</b></div>
          <div><span>Close</span><b className={tone(shape.change)}>{fmtPrice(bar.close)}</b></div>
        </div>
        <Rows rows={shapeRows} />
        <div className="candle-tip__section">
          <div className="candle-tip__head">Volume</div>
          <div className="candle-tip__row">
            <span>This candle</span>
            <span><b>{volume != null ? fmtVolume(volume) : '—'}</b> shares</span>
          </div>
          {meter != null && (
            <>
              <div className="candle-tip__meter" aria-hidden="true">
                <i style={{ width: `${meter * 100}%` }} />
                <u style={{ left: `${100 / CANDLE_HOVER_VOLUME_METER_MAX}%` }} />
              </div>
              <div className="candle-tip__scale" aria-hidden="true">
                <span style={{ left: `${100 / CANDLE_HOVER_VOLUME_METER_MAX}%` }}>avg</span>
                <span style={{ left: `${200 / CANDLE_HOVER_VOLUME_METER_MAX}%` }}>2×</span>
                <span style={{ left: '100%' }}>{CANDLE_HOVER_VOLUME_METER_MAX}×</span>
              </div>
            </>
          )}
          <Rows rows={volumeRows} />
        </div>
        {closedRows.length > 0 && (
          <div className="candle-tip__section">
            <div className="candle-tip__head">Where it closed</div>
            <Rows rows={closedRows} />
          </div>
        )}
      </CandleCard>
    </>
  );
}

/** The faint column behind the candle the card is about, the pane's full height. */
function CandleColumn({ chart, hover }: { chart: IChartApi; hover: CandleHover }) {
  const scale = chart.timeScale();
  const x = scale.logicalToCoordinate(hover.logical as Logical);
  if (x == null) return null;
  const next = scale.logicalToCoordinate((hover.logical + 1) as Logical);
  const width = Math.max(3, next != null ? next - x : scale.options().barSpacing);
  return (
    <div
      className="candle-tip__column"
      style={{ left: x - width / 2, width, bottom: scale.height() }}
      aria-hidden="true"
    />
  );
}

interface CandleCardProps {
  hover: CandleHover;
  chart: IChartApi;
  containerRef: RefObject<HTMLElement | null>;
  children: ReactNode;
}

const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), Math.max(low, high));

/**
 * The card beside the pointer, on its left near the price axis. It floats above the pane -- portalled as the
 * chart menu is, into the fullscreen element while the chart is fullscreen -- so a short grid pane never cuts
 * it off, and it stays inside the window.
 */
function CandleCard({ hover, chart, containerRef, children }: CandleCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [cardH, setCardH] = useState(0);
  // Rows come and go with the candle: measure again whenever the content changes, before it paints.
  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 0;
    if (h !== cardH) setCardH(h);
  }, [children, cardH]);
  const pane = containerRef.current;
  const target = chartContextMenuPortalTarget(pane);
  if (!pane || !target) return null;
  const box = pane.getBoundingClientRect();
  const plotW = chart.timeScale().width() || hover.width;
  const flip = hover.x + CANDLE_HOVER_CARD_GAP_PX + CANDLE_HOVER_CARD_W_PX > plotW;
  const paneLeft = flip ? hover.x - CANDLE_HOVER_CARD_GAP_PX - CANDLE_HOVER_CARD_W_PX : hover.x + CANDLE_HOVER_CARD_GAP_PX;
  const left = clamp(box.left + paneLeft, CANDLE_HOVER_EDGE_PX, window.innerWidth - CANDLE_HOVER_CARD_W_PX - CANDLE_HOVER_EDGE_PX);
  const top = clamp(box.top + hover.y - cardH / 2, CANDLE_HOVER_EDGE_PX, window.innerHeight - cardH - CANDLE_HOVER_EDGE_PX);
  return createPortal(
    <div ref={ref} className="candle-tip" style={{ left, top, width: CANDLE_HOVER_CARD_W_PX }} role="tooltip" data-testid="candle-hover-tip">
      {children}
    </div>,
    target,
  );
}
