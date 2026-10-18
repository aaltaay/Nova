import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { useChartInstance } from '../useChartInstance';
import { afterPaintSettles, paintFull } from '../chartBarsPaint';
import { rawBarsToSeries } from '../../tickerChartData';
import { FillMarkersPrimitive } from '../FillMarkersPrimitive';
import { drawCausalOverlay, exportGallery, type Pane } from './exportCanvas';
import { annotationSummary, contextLabel, entryTimeframes, entryTitle, paneBars, priceLineOptions,
  tradeMarkers } from './annotations';
import { readGallery } from './galleryContract';
import type { Entry, Gallery, PaneTimeframe } from './types';

const panes = new Map<string, Pane>();
const metrics: Record<string, number> = {};

declare global {
  interface Window {
    novaCharts?: { ready: boolean; error?: string; metrics: Record<string, number>;
      entries: Entry[]; exportPng: (index?: number) => { data: string; export_ms: number } };
  }
}
function PaneView({ entry, timeframe, done }: { entry: Entry; timeframe: PaneTimeframe; done: () => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const chart = useChartInstance({ containerRef, chartRef, candleSeriesRef, volSeriesRef,
    chartHeight: 380, fillParentHeight: false, maximized: false, timeframe });
  useEffect(() => {
    const overlay = overlayRef.current;
    const container = containerRef.current;
    if (!chart || !overlay || !container) return;
    let frame = 0;
    const draw = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const width = container.clientWidth, height = container.clientHeight;
        overlay.width = width * devicePixelRatio; overlay.height = height * devicePixelRatio;
        const ctx = overlay.getContext('2d');
        if (ctx && width && height) drawCausalOverlay({ chart, entry, timeframe }, ctx, width, height);
      });
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(draw);
    const observer = new ResizeObserver(draw); observer.observe(container); draw();
    return () => { cancelAnimationFrame(frame); observer.disconnect(); chart.timeScale().unsubscribeVisibleLogicalRangeChange(draw); };
  }, [chart, entry, timeframe]);
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!chart || !candleSeries) return;
    const { candles, volumes } = rawBarsToSeries(paneBars(entry, timeframe), timeframe);
    paintFull(candles, volumes, candleSeriesRef, volSeriesRef, chartRef, timeframe, null, { current: 0 });
    const lines = priceLineOptions(entry.annotations).map(options => candleSeries.createPriceLine(options));
    const fills = new FillMarkersPrimitive();
    candleSeries.attachPrimitive(fills);
    fills.setMarkers(tradeMarkers(entry, timeframe));
    const cancel = afterPaintSettles(() => {
      chart.timeScale().fitContent();
      requestAnimationFrame(() => {
        panes.set(`${entry.id}:${timeframe}`, { chart, entry, timeframe }); done();
      });
    });
    return () => {
      cancel(); panes.delete(`${entry.id}:${timeframe}`);
      lines.forEach(line => candleSeries.removePriceLine(line)); candleSeries.detachPrimitive(fills);
    };
  }, [chart, entry, timeframe, done]);
  return <div><div style={{ color: '#c2ccdb', padding: 4 }}>{timeframe} | volume | ET</div>
    <div style={{ position: 'relative' }}><div ref={containerRef} />
      <canvas ref={overlayRef} aria-hidden="true" data-testid="causal-context-overlay"
        data-entry-id={entry.id} data-timeframe={timeframe}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
    </div></div>;
}
function App() {
  const [gallery, setGallery] = useState<Gallery | null>(null);
  const [error, setError] = useState('');
  const painted = useRef(new Set<string>());
  useEffect(() => {
    const api = new URLSearchParams(location.search).get('api') || 'http://127.0.0.1:8009';
    const url = new URL(api);
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) { setError('Gateway must be local'); return; }
    const start = performance.now();
    fetch(`${url.origin}/api/agent/chart-gallery`).then(async response => {
      if (!response.ok) throw new Error(`Gateway HTTP${response.status}`);
      const data = readGallery(await response.json());
      metrics.fetch_ms = performance.now() - start;
      metrics.paint_started = performance.now();
      metrics.aggregation_ms = data.timings.aggregation_ms;
      setGallery(data);
    }).catch(err => { setError(String(err)); window.novaCharts = { ready: false, error: String(err), metrics, entries: [], exportPng: () => { throw err; } }; });
  }, []);
  function ready(key: string) {
    painted.current.add(key);
    const paneCount = gallery?.entries.reduce((sum, entry) => sum + entryTimeframes(entry).length, 0);
    if (!gallery || painted.current.size !== paneCount) return;
    metrics.paint_ms = performance.now() - metrics.paint_started;
    window.novaCharts = { ready: true, metrics, entries: gallery.entries, exportPng: (index?: number) => {
      const started = performance.now(); const data = exportGallery(gallery, panes, index);
      return { data, export_ms: performance.now() - started };
    } };
  }
  if (error) return <pre role="alert">{error}</pre>;
  if (!gallery) return <p>Loading frozen Nova chart data.</p>;
  return <main style={{ padding: 20 }}><h1>Nova | historical OHLCV gallery</h1>
    <p>Historical OHLCV | gaps preserved | native Nova renderer</p>
    <p>{gallery.family} | selection SHA256 {gallery.selection_sha256}</p>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 20 }}>
      {gallery.entries.map(entry => <section key={entry.id} style={{ background: '#161921', padding: 12 }}>
        <h2>{entryTitle(entry)}</h2><p>{contextLabel(entry)}</p>
        <p>{annotationSummary(entry.annotations) || 'No annotations'}</p>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${entryTimeframes(entry).length}, 1fr)`, gap: 10 }}>
          {entryTimeframes(entry).map(tf => <PaneView key={tf} entry={entry} timeframe={tf} done={() => ready(`${entry.id}:${tf}`)} />)}
        </div>
      </section>)}
    </div></main>;
}
createRoot(document.getElementById('root')!).render(<App />);
