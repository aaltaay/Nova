/**
 * The heat map in place of the Trader's four charts (ADR 061; operator-approved mockup v3, 2026-10-20): Level 2 over
 * time as glowing lines, bursts of trades as dots, the book now on the right, volume underneath. It reads the store
 * the Trader's own depth and tape sockets feed (no line of its own) and redraws at most every HEAT_FRAME_MS, only
 * while shown and the window is visible, so the order path never waits on it (ADR 045).
 */
import { useEffect, useRef, useState } from 'react';
import { heatNow } from './heatFrame';
import {
  HEAT_BRIGHTNESS_LABEL,
  HEAT_BRIGHTNESS_TITLE,
  HEAT_CAP_LOG_BRIGHT,
  HEAT_CAP_LOG_DIM,
  HEAT_DOT_MIN_OPTIONS,
  HEAT_DOTS_TITLE,
  HEAT_FRAME_MS,
  HEAT_LEGEND_ASK,
  HEAT_LEGEND_BID,
  HEAT_LEGEND_HIDDEN,
  HEAT_LEGEND_MID,
  HEAT_LEGEND_PULLED,
  HEAT_LEGEND_TRADED,
  HEAT_MARKS_IDLE,
  HEAT_MARKS_TITLE,
  HEAT_MAX_DPR,
  HEAT_SCALE_FEW,
  HEAT_SCALE_MANY,
  HEAT_UNSEEN_NOTE,
  HEAT_WHEEL_STEP,
  HEAT_WINDOW_MAX_SEC,
  HEAT_WINDOW_MIN_SEC,
  HEAT_WINDOWS_SEC,
  heatDotsLabel,
  heatMarksOff,
  heatWindowLabel,
} from './heatMapConstants';
import { heatPrefs, setHeatPrefs, useHeatPrefs } from './heatMapPrefs';
import { paintHeat } from './heatPaint';
import { heatStatus } from './heatStatus';
import { heatOf } from './heatStore';
import { heatWatchState } from './heatWatch';
import { HeatMapToolbar } from './HeatMapToolbar';
import './heatMap.css';

/** log10 of the shares that read red at a brightness (0 dim .. 100 bright). */
export function heatCapLog(brightness: number): number {
  return HEAT_CAP_LOG_DIM + (HEAT_CAP_LOG_BRIGHT - HEAT_CAP_LOG_DIM) * (brightness / 100);
}

function nextDotSize(current: number): number {
  const opts = HEAT_DOT_MIN_OPTIONS as readonly number[];
  return opts[(opts.indexOf(current) + 1) % opts.length];
}

export function HeatMapView({ symbol, active }: { symbol: string; active: boolean }) {
  const prefs = useHeatPrefs();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  /** Why the traded / pulled marks are missing (the book watcher's own reason), or null while it watches. */
  const [marksOff, setMarksOff] = useState<string | null>(null);
  const sym = symbol.toUpperCase();

  useEffect(() => {
    if (!active) return undefined;
    let raf = 0;
    let last = 0;
    let drawn = '';
    const frame = (ts: number) => {
      raf = requestAnimationFrame(frame);
      if (ts - last < HEAT_FRAME_MS || document.hidden) return;
      last = ts;
      const wrap = wrapRef.current;
      const canvas = canvasRef.current;
      if (!wrap || !canvas) return;
      const s = heatOf(sym);
      const wallMs = Date.now();
      const next = heatStatus(s, sym, wallMs);
      setStatus((prev) => (prev === next ? prev : next));
      const watch = heatWatchState(sym);
      const off = watch && !watch.watching ? (watch.reason ?? HEAT_MARKS_IDLE) : null;
      setMarksOff((prev) => (prev === off ? prev : off));
      const cssW = Math.max(1, wrap.clientWidth);
      const cssH = Math.max(1, wrap.clientHeight);
      const dpr = Math.min(HEAT_MAX_DPR, window.devicePixelRatio || 1);
      const bw = Math.round(cssW * dpr);
      const bh = Math.round(cssH * dpr);
      if (canvas.width !== bw || canvas.height !== bh) {
        canvas.width = bw;
        canvas.height = bh;
        drawn = '';
      }
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      if (!s) {
        if (drawn !== 'none') {
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          ctx.fillStyle = '#000';
          ctx.fillRect(0, 0, bw, bh);
          drawn = 'none';
        }
        return;
      }
      const p = heatPrefs();
      const t1 = heatNow(s, wallMs);
      const perPx = p.windowSec / cssW;
      // Redraw only when the data moved, the clock moved a pixel, or a choice or the size changed.
      const key = `${s.version}|${Math.floor(t1 / perPx)}|${bw}x${bh}|${p.windowSec}|${p.minDot}|${p.brightness}`;
      if (key === drawn) return;
      drawn = key;
      paintHeat(ctx, s, { t0: t1 - p.windowSec, t1 }, cssW, cssH, dpr, { minDot: p.minDot, capLog: heatCapLog(p.brightness) });
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [sym, active]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return undefined;
    // The mouse wheel zooms the window (not the page): native listener, so it may prevent the scroll.
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const cur = heatPrefs().windowSec;
      const next = e.deltaY > 0 ? cur * HEAT_WHEEL_STEP : cur / HEAT_WHEEL_STEP;
      setHeatPrefs({ windowSec: Math.round(Math.min(HEAT_WINDOW_MAX_SEC, Math.max(HEAT_WINDOW_MIN_SEC, next))) });
    };
    wrap.addEventListener('wheel', onWheel, { passive: false });
    return () => wrap.removeEventListener('wheel', onWheel);
  }, []);

  const preset = (HEAT_WINDOWS_SEC as readonly number[]).includes(prefs.windowSec);
  return (
    <div className="heat-map" data-testid="heat-map">
      <div className="heat-map__bar">
        <HeatMapToolbar testId="heat-map-back" />
        <span className="heat-map__sym">{sym}</span>
        <span className="heat-map__scale">
          {HEAT_SCALE_FEW}
          <i aria-hidden="true" />
          {HEAT_SCALE_MANY}
        </span>
        <span className="heat-map__lg"><b className="heat-ball heat-ball--ask" aria-hidden="true" />{HEAT_LEGEND_ASK}</span>
        <span className="heat-map__lg"><b className="heat-ball heat-ball--bid" aria-hidden="true" />{HEAT_LEGEND_BID}</span>
        <span className="heat-map__lg"><b className="heat-ball heat-ball--mid" aria-hidden="true" />{HEAT_LEGEND_MID}</span>
        <span
          className={`heat-map__marks${marksOff != null ? ' heat-map__marks--off' : ''}`}
          title={marksOff != null ? heatMarksOff(marksOff) : HEAT_MARKS_TITLE}
          data-testid="heat-map-marks"
        >
          <span className="heat-map__lg"><b className="heat-mk heat-mk--traded" aria-hidden="true">✓</b>{HEAT_LEGEND_TRADED}</span>
          <span className="heat-map__lg"><b className="heat-mk heat-mk--pulled" aria-hidden="true">✕</b>{HEAT_LEGEND_PULLED}</span>
          <span className="heat-map__lg"><b className="heat-mk heat-mk--hidden" aria-hidden="true">◆</b>{HEAT_LEGEND_HIDDEN}</span>
        </span>
        <span className="heat-map__note">{HEAT_UNSEEN_NOTE}</span>
        <div className="heat-map__ctl">
          <button
            type="button"
            className="heat-map__chip"
            title={HEAT_DOTS_TITLE}
            onClick={() => setHeatPrefs({ minDot: nextDotSize(prefs.minDot) })}
            data-testid="heat-map-dots"
          >
            {heatDotsLabel(prefs.minDot)}
          </button>
          <span className="heat-map__sep" aria-hidden="true" />
          {HEAT_WINDOWS_SEC.map((sec) => (
            <button
              key={sec}
              type="button"
              className={`heat-map__chip${prefs.windowSec === sec ? ' heat-map__chip--on' : ''}`}
              aria-pressed={prefs.windowSec === sec}
              onClick={() => setHeatPrefs({ windowSec: sec })}
            >
              {heatWindowLabel(sec)}
            </button>
          ))}
          {!preset ? <span className="heat-map__zoom">{heatWindowLabel(prefs.windowSec)}</span> : null}
          <label className="heat-map__bright" title={HEAT_BRIGHTNESS_TITLE}>
            {HEAT_BRIGHTNESS_LABEL}
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={prefs.brightness}
              onChange={(e) => setHeatPrefs({ brightness: Number(e.target.value) })}
              aria-label={HEAT_BRIGHTNESS_LABEL}
            />
          </label>
        </div>
      </div>
      <div className="heat-map__stage" ref={wrapRef}>
        <canvas ref={canvasRef} className="heat-map__canvas" aria-label={`${sym} heat map`} />
        {status ? <div className="heat-map__status" role="status">{status}</div> : null}
      </div>
    </div>
  );
}
