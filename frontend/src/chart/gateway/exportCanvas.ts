import type { IChartApi, Time } from 'lightweight-charts';
import { captureChartCanvas } from '../chartSnapshot';
import type { Entry, Gallery } from './types';
import { annotationColor, annotationSummary, clock, contextLabel, entryTitle } from './annotations';
import { causalBoundary } from './causalBoundary';

export interface Pane { chart: IChartApi; entry: Entry; timeframe: '1Min' | '5Min' }

function wallTime(entry: Entry, minute: number): Time {
  return (Date.parse(`${entry.date}T00:00:00Z`) / 1000 + minute * 60) as Time;
}

/** Same generic annotations and optional context mask for the page and PNG. */
export function drawCausalOverlay(pane: Pane, ctx: CanvasRenderingContext2D, width: number, height: number): void {
  const ratio = ctx.canvas.width / width;
  const pixelHeight = height * ratio;
  const plotWidth = Math.max(0, width - pane.chart.priceScale('right').width());
  const data = pane.timeframe === '1Min' ? pane.entry.bars_1m : pane.entry.bars_5m;
  const boundary = pane.entry.as_of_m == null ? null : causalBoundary(data, pane.entry.as_of_t, pane.timeframe,
    time => pane.chart.timeScale().timeToCoordinate(time), pane.chart.timeScale().options().barSpacing, plotWidth);
  if (boundary != null) {
    const future = boundary.x * ratio;
    if (boundary.hasFuture) { ctx.fillStyle = 'rgba(242,156,82,0.17)'; ctx.fillRect(future, 0, plotWidth * ratio - future, pixelHeight); }
    ctx.strokeStyle = '#ffbc79'; ctx.lineWidth = 2 * ratio; ctx.setLineDash([5 * ratio, 4 * ratio]);
    ctx.beginPath(); ctx.moveTo(future, 0); ctx.lineTo(future, pixelHeight); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#ffd6ad'; ctx.font = `${13 * ratio}px Arial`;
    ctx.fillText(`As of ${clock(pane.entry.as_of_m!)}`, Math.max(4, future - 110 * ratio), 17 * ratio);
  }
  for (const annotation of pane.entry.annotations) {
    if (annotation.kind !== 'time_marker') continue;
    const position = pane.chart.timeScale().timeToCoordinate(wallTime(pane.entry, annotation.minute));
    // No invented candles or interpolated coordinate through missing data.
    // Complete annotation text stays in the page and export caption.
    if (position == null || position < 0 || position > plotWidth) continue;
    const x = position * ratio;
    ctx.strokeStyle = annotationColor(annotation.color); ctx.lineWidth = ratio; ctx.setLineDash([3 * ratio, 3 * ratio]);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, pixelHeight); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = annotationColor(annotation.color); ctx.font = `${12 * ratio}px Arial`;
    ctx.fillText(annotation.label, Math.max(4, x + 4 * ratio), 35 * ratio);
  }
}

export function paneImage(pane: Pane, width: number, height: number): HTMLCanvasElement {
  const oldWidth = pane.chart.chartElement().clientWidth;
  const oldHeight = pane.chart.chartElement().clientHeight;
  try {
    pane.chart.resize(width, height, true);
    pane.chart.timeScale().fitContent();
    const native = captureChartCanvas(pane.chart);
    const result = document.createElement('canvas');
    result.width = native.width; result.height = native.height;
    const ctx = result.getContext('2d')!;
    ctx.drawImage(native, 0, 0);
    drawCausalOverlay(pane, ctx, width, height);
    return result;
  } finally {
    pane.chart.resize(oldWidth, oldHeight, true);
    pane.chart.timeScale().fitContent();
  }
}

function textRows(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const rows: string[] = [];
  let row = '';
  for (const word of text.split(' ')) {
    const next = row ? `${row} ${word}` : word;
    if (row && ctx.measureText(next).width > width) { rows.push(row); row = word; }
    else row = next;
  }
  if (row) rows.push(row);
  return rows;
}

/** Compose Nova's native candle canvases; never derive or draw candles here. */
export function exportGallery(gallery: Gallery, panes: Map<string, Pane>, index?: number): string {
  const entries = gallery.entries;
  const chosen = index == null ? entries : [entries[index]];
  if (!chosen[0]) throw new Error('Unknown gallery example');
  const cols = index == null ? Math.min(3, chosen.length) : 1;
  const cardW = index == null ? 1000 : 1800;
  const plotHeight = index == null ? 535 : 865;
  const captionSize = index == null ? 17 : 23;
  const lineHeight = captionSize + 6;
  const canvas = document.createElement('canvas');
  canvas.width = cols * cardW;
  const ctx = canvas.getContext('2d')!;
  ctx.font = `${captionSize}px Arial`;
  const captions = chosen.map(entry => textRows(ctx, annotationSummary(entry.annotations) || 'No annotations', cardW - 40));
  const chartTop = Math.max(138, 110 + Math.max(...captions.map(rows => rows.length)) * lineHeight);
  const cardH = chartTop + plotHeight + 45;
  canvas.height = 100 + Math.ceil(chosen.length / cols) * cardH + 65;
  ctx.fillStyle = '#10131b'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#f1f5f9'; ctx.font = 'bold 29px Arial';
  ctx.fillText(`Nova | ${entries.length} historical OHLCV entries`, 25, 40);
  ctx.fillStyle = '#c4cad7'; ctx.font = '19px Arial';
  ctx.fillText(gallery.family, 25, 73);
  chosen.forEach((entry, i) => {
    const x = i % cols * cardW; const y = 100 + Math.floor(i / cols) * cardH;
    ctx.fillStyle = '#eef2f8'; ctx.font = `bold ${index == null ? 25 : 32}px Arial`;
    ctx.fillText(entryTitle(entry), x + 20, y + 35);
    ctx.fillStyle = '#b8c8dc'; ctx.font = `${captionSize}px Arial`;
    ctx.fillText(contextLabel(entry), x + 20, y + 66);
    captions[i].forEach((line, row) => ctx.fillText(line, x + 20, y + 94 + row * lineHeight));
    for (const [j, tf] of (['1Min', '5Min'] as const).entries()) {
      const pane = panes.get(`${entry.id}:${tf}`);
      if (!pane) throw new Error('Native chart pane is not ready');
      const chartX = x + 15 + j * cardW / 2;
      ctx.fillStyle = '#edf4ff'; ctx.font = 'bold 22px Arial';
      ctx.fillText(tf === '1Min' ? '1-minute + volume' : '5-minute + volume', chartX, y + chartTop - 12);
      ctx.drawImage(paneImage(pane, cardW / 2 - 30, plotHeight), chartX, y + chartTop, cardW / 2 - 30, plotHeight);
    }
    ctx.fillStyle = '#bdc5d4'; ctx.font = '16px Arial';
    ctx.fillText('Historical OHLCV | raw same-session units | missing bars remain gaps', x + 20, y + cardH - 15);
  });
  ctx.fillStyle = '#b5bfce'; ctx.font = '16px Arial';
  ctx.fillText(`Selection SHA256 ${gallery.selection_sha256}`, 25, canvas.height - 25);
  return canvas.toDataURL('image/png');
}
