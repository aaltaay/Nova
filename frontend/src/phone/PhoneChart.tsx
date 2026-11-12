/**
 * The desk's own chart (`TickerChart`), in a phone-sized box. Bars, the forming candle, EMAs, the
 * session VWAP, MACD, your average-price line and the lines drawn on the desk are all the desk
 * chart's; the phone hides its header and supplies the switches itself (`phoneDesk.css`).
 *
 * What the phone chart cannot do yet, said where the control is:
 * - the 10-second chart follows the tape, which the phone opens only on the Trade screen;
 * - drawing saves to the desk, and the phone's door has no route for that yet.
 */
import { useCallback, useState } from 'react';
import { TickerChart } from '../chart';
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

export function PhoneChart({ symbol, frame, indicators, onIndicatorToggle }: {
  symbol: string;
  frame: string;
  indicators: ChartIndicatorId[];
  onIndicatorToggle: (id: ChartIndicatorId) => void;
}) {
  return (
    <div className="ph-chart" data-testid="phone-chart" data-frame={frame}>
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
      />
    </div>
  );
}
