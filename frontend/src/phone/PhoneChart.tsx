/**
 * The desk's own chart (`TickerChart`), in a phone-sized box. Bars, the forming candle, EMAs, the
 * session VWAP, MACD, your average-price line and the lines drawn on the desk are all the desk
 * chart's; the phone hides its header and supplies the switches itself (`phoneDesk.css`).
 *
 * The desk pane's right-click menu is left out (`contextMenu={false}`): a long press must not open a menu whose
 * Buy and Sell stage the desk's ticket, and the menu reads bot routes another device may not.
 *
 * What the phone chart cannot do yet, said where the control is:
 * - the 10-second chart follows the tape, which the phone opens only on the Trade screen;
 * - drawing saves to the desk, and the phone's door has no route for that yet.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { LogicalRange } from 'lightweight-charts';
import { TickerChart, claimEdge, type ChartPaneOverlayProps } from '../chart';
import { CHART_INDICATORS, type ChartIndicatorId } from '../constants';
import { readPref, writePref } from '../utils/prefStore';

export interface PhoneFrame {
  id: string;
  name: string;
  /** Why it cannot be chosen yet; absent when it can. */
  notYet?: string;
}

export const TAPE_FIRST = 'The 10-second chart follows the tape, which opens with the Trade screen.';

export const PHONE_FRAMES: readonly PhoneFrame[] = [
  { id: '10Sec', name: '10s', notYet: TAPE_FIRST },
  { id: '1Min', name: '1m' },
  { id: '5Min', name: '5m' },
  { id: '1Day', name: 'D' },
];

/** Kept on the phone: owner this file, `utils/prefStore` envelopes; an unknown value reads as the default. */
const FRAME_KEY = 'nova.phone.chart.frame';
const INDICATORS_KEY = 'nova.phone.chart.indicators';
const DEFAULT_INDICATORS: ChartIndicatorId[] = ['emas', 'vwap'];
const KNOWN = new Set<string>(CHART_INDICATORS.map((o) => o.id));

function readFrame(): string {
  return readPref<string>(FRAME_KEY, '1Min', (raw) => (PHONE_FRAMES.some((f) => f.id === raw && !f.notYet) ? (raw as string) : null));
}

function readIndicators(): ChartIndicatorId[] {
  return readPref<ChartIndicatorId[]>(INDICATORS_KEY, DEFAULT_INDICATORS, (raw) =>
    (Array.isArray(raw) && raw.every((id) => typeof id === 'string' && KNOWN.has(id)) ? (raw as ChartIndicatorId[]) : null));
}

/** The chart's timeframe and what it draws: one choice for the stock page and the big chart, kept on the phone. */
export function usePhoneChartPrefs() {
  const [frame, setFrameState] = useState<string>(readFrame);
  const [indicators, setIndicators] = useState<ChartIndicatorId[]>(readIndicators);
  const setFrame = useCallback((next: string) => {
    writePref(FRAME_KEY, next);
    setFrameState(next);
  }, []);
  const toggleIndicator = useCallback((id: ChartIndicatorId) => {
    setIndicators((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      writePref(INDICATORS_KEY, next);
      return next;
    });
  }, []);
  return { frame, setFrame, indicators, toggleIndicator };
}

export function FrameSwitch({ frame, onFrame }: { frame: string; onFrame: (id: string) => void }) {
  return (
    <div className="ph-seg ph-frames" role="group" aria-label="Timeframe">
      {PHONE_FRAMES.map((f) => (
        <button
          key={f.id}
          type="button"
          aria-pressed={f.id === frame}
          disabled={Boolean(f.notYet)}
          data-why={f.notYet}
          onClick={() => onFrame(f.id)}
        >
          {f.name}
        </button>
      ))}
    </div>
  );
}

/** One candle about every this many pixels on first paint. */
const PX_PER_BAR = 6;
const MIN_BARS = 20;
/**
 * The price scale: as narrow as the numbers on it. The least it may be holds a price like "4.82" and the
 * candle's countdown ("00:26", drawn on the scale under the last price); a longer price or a volume figure
 * widens it by what it needs (operator, 2026-11-12: "make them more compact ... don't forget the countdown").
 */
const SCALE_WIDTH_PX = 36;
const SCALE_FONT_PX = 10;

/**
 * What makes the desk's chart fit a phone box. Each is asked of the chart through its own surface, so the chart
 * stays the desk's:
 *
 * - The price scale. The desk reserves 96 px for it, so a growing volume chip never shoves the plot; in a phone
 *   box that is a quarter of the chart. Here it keeps a fixed width sized to the phone's smaller type.
 * - The lines' names. The desk writes "9 EMA", "VWAP $4.31" at the right edge, over the newest candles of a
 *   narrow pane. The phone names the lines in its own legend row, so it claims the edge (chart/edgeWords), which
 *   is how any pane tells the series to leave their titles to it.
 * - The first view. The desk opens a 1-minute pane on its last 500 candles; here that is under a pixel a candle.
 *   So once the desk has painted, the phone asks for as many of the newest candles as its width shows clearly,
 *   once per stock and timeframe. After that the view is the chart's own: it follows the newest candle, and a
 *   pinch or a drag is kept.
 */
function PhoneChartFit({ chart, candleSeriesRef, volSeriesRef, barsRevision, symbol, timeframe, mini }: ChartPaneOverlayProps & { mini?: boolean }) {
  const done = useRef<string | null>(null);

  useEffect(() => {
    if (!chart) return undefined;
    chart.applyOptions({ layout: { fontSize: SCALE_FONT_PX } });
    // The small chart on Trade is a strip a few candles tall: no time row and no logo, which the full
    // chart it opens carries.
    if (mini) {
      chart.applyOptions({ layout: { attributionLogo: false } });
      chart.timeScale().applyOptions({ visible: false });
      // The strip is three labels tall at most: the price and the countdown take two, so the volume figure
      // (it is in the header's day numbers) gives up its label. The bars stay.
      volSeriesRef?.current?.applyOptions({ lastValueVisible: false, priceLineVisible: false });
    }
    // No tick marks: on a scale this narrow they are four pixels of nothing beside every number.
    chart.priceScale('right').applyOptions({ minimumWidth: SCALE_WIDTH_PX, ticksVisible: false });
    chart.priceScale('volume').applyOptions({ minimumWidth: SCALE_WIDTH_PX, ticksVisible: false });
    return claimEdge(chart);
  }, [chart, mini, volSeriesRef]);

  useEffect(() => {
    const key = `${symbol}:${timeframe}`;
    if (!chart || done.current === key) return undefined;
    // After the desk's own paint of this revision, which runs after this effect.
    const frame = window.requestAnimationFrame(() => {
      const count = candleSeriesRef.current?.data().length ?? 0;
      // The small chart hides its time row, whose width then reads 0: the pane is as wide.
      const width = chart.timeScale().width() || chart.paneSize().width;
      if (!count || !(width > 0)) return;
      done.current = key;
      const keep = Math.max(MIN_BARS, Math.round(width / PX_PER_BAR));
      if (count > keep) chart.timeScale().setVisibleLogicalRange({ from: count - keep, to: count + 1 } as LogicalRange);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [chart, candleSeriesRef, barsRevision, symbol, timeframe]);
  return null;
}

const renderFit = (props: ChartPaneOverlayProps) => <PhoneChartFit {...props} />;
const renderMiniFit = (props: ChartPaneOverlayProps) => <PhoneChartFit {...props} mini />;

export function PhoneChart({ symbol, frame, indicators, onIndicatorToggle, mini = false }: {
  symbol: string;
  frame: string;
  indicators: ChartIndicatorId[];
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  /** The strip on the Trade screen: candles and lines only. */
  mini?: boolean;
}) {
  return (
    <div className="ph-chart" data-testid="phone-chart" data-frame={frame} data-mini={mini ? 'true' : 'false'}>
      <TickerChart
        key={frame}
        symbol={symbol}
        followTicker
        variant="grid"
        compactChrome
        fixedTimeframe={frame}
        indicators={indicators}
        onIndicatorToggle={onIndicatorToggle}
        activeTool={null}
        renderPaneOverlay={mini ? renderMiniFit : renderFit}
        countdownOnScale
        contextMenu={false}
      />
    </div>
  );
}
