/**
 * Ahead on a Trader chart pane (ADR 065): drawn on the 1-minute pane only, while the toolbar's Ahead switch is on.
 *
 * The layer gathers what the scene needs -- the switch and scope, the backend's answer (`useAheadAnswer`, asked
 * only while on), the stock read the page already holds (Nova's lines, zones and setup lanes), the chart's own
 * completed candles, whether the MACD pane is there and whether the zone has room -- builds the scene once
 * (`aheadScene.ts`: every gate and word) and hands it to the primitives: the zone on the candle series, the ghost
 * volume on the volume histogram and the MACD fan on the MACD pane. The heading's words are DOM over the zone. The
 * scene is also published per symbol for the Ahead panel, so its numbers are the ones on the chart, with the part of
 * the screen the panel must leave clear (`aheadSheetPlace.ts`). Switched on, and on each new answer, the pane is framed
 * for the zone unless the operator owns the view (`useAheadRoom.ts`).
 */
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import type { ISeriesApi } from 'lightweight-charts';
import type { ChartPaneOverlayProps } from '../chart';
import { useSimReplayDesk, useSimReplayPlayhead } from '../sim';
import { publishPaneKeySection, useStockReadContext } from '../stock_read';
import { etChartSeconds } from '../tickerChartData';
import { AheadHeading, type HeadingHandle } from './AheadHeading';
import { AheadPrimitive, type ZoneLayout } from './AheadPrimitive';
import { AheadVolumePrimitive } from './AheadVolumePrimitive';
import { AHEAD_RECENT_VOLUME_BARS, AHEAD_STEP_SEC, AHEAD_TIMEFRAME, AHEAD_WORDS } from './aheadConstants';
import { aheadKeySection } from './aheadKeyRows';
import { aheadScene } from './aheadScene';
import type { AheadScene } from './aheadSceneTypes';
import { useAheadPrefs } from './aheadPrefs';
import { useAheadAnswer } from './useAheadAnswer';
import { useAheadMacd, useMacdPane } from './useAheadMacd';
import { publishKeepClear } from './aheadSheetPlace';
import { useAheadRoom } from './useAheadRoom';

const CLOCK_BEAT_MS = 1000;
/** Ahead's section on the pane's Key (`stock_read/paneKeyExtras.ts`). */
const AHEAD_KEY_SOURCE = 'ahead';

// ---------------------------------------------------------------- the scene per symbol, for the panel

const scenes = new Map<string, AheadScene>();
const sceneListeners = new Set<() => void>();

/** The 1-minute pane's scene for `symbol` (null: no such pane draws Ahead). */
export function publishAheadScene(symbol: string, scene: AheadScene | null): void {
  if ((scenes.get(symbol) ?? null) === scene) return;
  if (scene) scenes.set(symbol, scene);
  else scenes.delete(symbol);
  for (const fn of [...sceneListeners]) fn();
}

function subscribeScenes(fn: () => void): () => void {
  sceneListeners.add(fn);
  return () => {
    sceneListeners.delete(fn);
  };
}

/** The scene the 1-minute pane of `symbol` draws now; null while no 1-minute pane draws Ahead. */
export function useAheadSceneOf(symbol: string): AheadScene | null {
  return useSyncExternalStore(subscribeScenes, () => scenes.get(symbol) ?? null);
}

// ---------------------------------------------------------------- the desk's minute and the chart's candles

/** The desk clock's minute (the playhead on a replay), read once a second while `on`; null while off. */
function useDeskMinute(on: boolean, playhead: number | null): number | null {
  const [liveMinute, setLiveMinute] = useState(() => Math.floor(Date.now() / 60_000));
  useEffect(() => {
    if (!on || playhead !== null) return undefined;
    const id = window.setInterval(() => setLiveMinute(Math.floor(Date.now() / 60_000)), CLOCK_BEAT_MS);
    return () => window.clearInterval(id);
  }, [on, playhead]);
  if (!on) return null;
  return playhead !== null ? Math.floor(playhead / 60) : liveMinute;
}

/** The pane's completed candles (chart seconds): every candle whose minute had ended by the desk clock. */
export function completedCandles(series: ISeriesApi<'Candlestick'> | null, deskMinute: number | null): { t: number; c: number }[] {
  if (!series || deskMinute === null) return [];
  const cutoff = etChartSeconds(deskMinute * 60_000);
  const out: { t: number; c: number }[] = [];
  for (const row of series.data()) {
    const t = Number(row.time);
    const c = (row as { close?: number }).close;
    if (t + AHEAD_STEP_SEC <= cutoff && typeof c === 'number' && Number.isFinite(c)) out.push({ t, c });
  }
  return out;
}

/** The last real completed 1-minute volumes, oldest first (the panel's volume chart). */
export function recentVolumes(series: ISeriesApi<'Histogram'> | null, deskMinute: number | null): number[] {
  if (!series || deskMinute === null) return [];
  const cutoff = etChartSeconds(deskMinute * 60_000);
  const out: number[] = [];
  for (const row of series.data()) {
    const v = (row as { value?: number }).value;
    if (Number(row.time) + AHEAD_STEP_SEC <= cutoff && typeof v === 'number' && Number.isFinite(v)) out.push(v);
  }
  return out.slice(-AHEAD_RECENT_VOLUME_BARS);
}

// ---------------------------------------------------------------- the layer

/** The pane and its zone (to the pane's right edge, its price axis included), in client pixels: the Ahead panel
 * never covers them. */
function keepClearOf(chart: NonNullable<ChartPaneOverlayProps['chart']>, z: NonNullable<ZoneLayout>) {
  const el = typeof chart.chartElement === 'function' ? chart.chartElement() : null;
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { left: r.left + z.left, right: r.right, paneLeft: r.left, paneRight: r.right };
}

export function AheadChartLayer({ symbol, timeframe, chart, candleSeriesRef, barsRevision,
  volSeriesRef }: ChartPaneOverlayProps) {
  const prefs = useAheadPrefs();
  const paneIs1m = timeframe === AHEAD_TIMEFRAME;
  const on = prefs.shown && paneIs1m;
  const series = chart ? candleSeriesRef.current : null;
  const volSeries = chart ? volSeriesRef?.current ?? null : null;
  const ctx = useStockReadContext();
  // Only the visible tab asks (a Trader tab in the background keeps its pane mounted).
  const { answer, fetchProblem } = useAheadAnswer(symbol, on && (ctx?.active ?? true));
  const read = on ? ctx?.readNow ?? null : null;
  const replay = useSimReplayDesk();
  const playhead = useSimReplayPlayhead();
  const deskMinute = useDeskMinute(on, replay ? playhead : null);
  const candles = useMemo(
    () => completedCandles(series, deskMinute),
    [series, deskMinute, barsRevision, answer?.bar_t], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const recentVolume = useMemo(
    () => recentVolumes(volSeries as ISeriesApi<'Histogram'> | null, deskMinute),
    [volSeries, deskMinute, barsRevision], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const replayEmpty = on && replay && barsRevision > 0 && !!series && series.data().length === 0;
  const roomOk = useAheadRoom(chart, series, on, barsRevision, answer?.as_of ?? null);
  const macdPane = useMacdPane(chart, on);
  const scene = useMemo(() => aheadScene({
    symbol, prefs, paneIs1m, answer, fetchProblem, read, candles, macdOn: macdPane !== null, roomOk, replayEmpty,
    recentVolume,
  }), [symbol, prefs, paneIs1m, answer, fetchProblem, read, candles, macdPane, roomOk, replayEmpty, recentVolume]);
  const fanDim = prefs.scope === 'flat_top' || prefs.scope === 'first_pullback';

  // The panel reads this pane's scene (a 1-minute pane only).
  useEffect(() => {
    if (!paneIs1m) return undefined;
    publishAheadScene(symbol, scene);
    return () => publishAheadScene(symbol, null);
  }, [symbol, paneIs1m, scene]);

  // The heading follows the zone without a React render per frame.
  const heading = useRef<HeadingHandle | null>(null);
  const onLayout = useCallback((z: ZoneLayout) => {
    heading.current?.place(z, chart?.timeScale().height() ?? 0);
    publishKeepClear(symbol, z && chart ? keepClearOf(chart, z) : null);
  }, [chart, symbol]);
  useEffect(() => {
    if (!on || !paneIs1m) return undefined;
    return () => publishKeepClear(symbol, null);
  }, [on, paneIs1m, symbol]);

  const primitive = useRef<AheadPrimitive | null>(null);
  useEffect(() => {
    if (!series || !on) return undefined;
    const p = new AheadPrimitive();
    series.attachPrimitive(p);
    p.setLayoutListener(onLayout);
    primitive.current = p;
    return () => {
      p.setLayoutListener(null);
      try {
        series.detachPrimitive(p);
      } catch {
        /* the series is gone with its chart */
      }
      if (primitive.current === p) primitive.current = null;
    };
  }, [series, on, onLayout]);
  useEffect(() => {
    primitive.current?.setScene(scene, fanDim);
  }, [scene, fanDim, series, on]);
  // The forecast's prices are drawn above the volume band.
  useEffect(() => {
    primitive.current?.setVolumeSeries(volSeries);
  }, [volSeries, series, on]);

  const ghost = useRef<AheadVolumePrimitive | null>(null);
  useEffect(() => {
    if (!volSeries || !on) return undefined;
    const p = new AheadVolumePrimitive();
    volSeries.attachPrimitive(p);
    ghost.current = p;
    return () => {
      try {
        volSeries.detachPrimitive(p);
      } catch {
        /* the series is gone with its chart */
      }
      if (ghost.current === p) ghost.current = null;
    };
  }, [volSeries, on]);
  useEffect(() => {
    ghost.current?.setScene(scene, AHEAD_WORDS.aiVolumeLabel);
  }, [scene, volSeries, on]);

  useAheadMacd(on ? macdPane : null, scene);

  // The pane's Key lists what the zone's marks mean while Ahead draws here, so the zone reads with the panel closed.
  const { legend, meet, chips, zone } = scene;
  const keySection = useMemo(() => aheadKeySection({ legend, meet, chips }, on && zone !== null),
    [legend, meet, chips, on, zone]);
  useEffect(() => {
    if (!chart) return undefined;
    publishPaneKeySection(chart, AHEAD_KEY_SOURCE, keySection);
    return () => publishPaneKeySection(chart, AHEAD_KEY_SOURCE, null);
  }, [chart, keySection]);

  const onHeadingSize = useCallback((rects: { left: number; top: number; right: number; bottom: number }[]) => {
    primitive.current?.setExtraWords(rects);
  }, []);

  if (!on) return null;
  return (
    <AheadHeading
      ref={heading}
      symbol={symbol}
      scene={scene}
      onSize={onHeadingSize}
    />
  );
}
