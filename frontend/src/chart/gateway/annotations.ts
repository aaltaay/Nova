import type { SeriesMarker, Time } from 'lightweight-charts';
import { timeframeSeconds } from '../../tickerChartData';
import type { Annotation, AnnotationColor, Entry, PaneTimeframe } from './types';

/** Fixed public palette; annotation inputs never become arbitrary CSS. */
export const ANNOTATION_COLORS: Record<AnnotationColor, string> = {
  blue: '#4da8ff', gold: '#e5b45b', grey: '#a2aab8', green: '#10b981', red: '#ef4444',
};
export const clock = (minute: number) => `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
const clockSeconds = (second: number) => `${clock(Math.floor(second / 60))}:${String(Math.floor(second % 60)).padStart(2, '0')}`;

export function annotationColor(color: AnnotationColor = 'blue'): string {
  if (!Object.hasOwn(ANNOTATION_COLORS, color)) throw new Error('Invalid annotation color');
  return ANNOTATION_COLORS[color];
}

export function priceLineOptions(annotations: Annotation[]) {
  return annotations.filter(annotation => annotation.kind === 'horizontal_line').map(annotation => ({
    price: annotation.price, title: annotation.label, color: annotationColor(annotation.color), lineWidth: 1 as const,
  }));
}

/** A minute entry shows 1Min + 5Min; a trade chart shows its one sub-minute pane. */
export function entryTimeframes(entry: Entry): PaneTimeframe[] {
  return entry.bar_seconds ? [`${entry.bar_seconds}Sec` as PaneTimeframe] : ['1Min', '5Min'];
}

export function paneBars(entry: Entry, timeframe: PaneTimeframe) {
  return timeframe === '1Min' ? entry.bars_1m : timeframe === '5Min' ? entry.bars_5m : entry.bars_sub ?? [];
}

/** Each caller fill on the bar that holds its second (chart time is ET wall clock as UTC, like the desk). */
export function tradeMarkers(entry: Entry, timeframe: PaneTimeframe): SeriesMarker<Time>[] {
  const midnight = Date.parse(`${entry.date}T00:00:00Z`) / 1000;
  const step = timeframeSeconds(timeframe);
  return entry.annotations.filter(a => a.kind === 'trade_marker').map((marker, index) => {
    const buy = marker.side === 'buy';
    return { time: (midnight + Math.floor(marker.second / step) * step) as Time,
      position: buy ? 'belowBar' : 'aboveBar', shape: buy ? 'arrowUp' : 'arrowDown',
      color: annotationColor(marker.color ?? (buy ? 'green' : 'red')), text: marker.label, id: `trade-${index}` };
  });
}

export function annotationSummary(annotations: Annotation[]): string {
  return annotations.map(annotation => annotation.kind === 'horizontal_line'
    ? `${annotation.label}: ${annotation.price.toFixed(4)}`
    : annotation.kind === 'trade_marker'
      ? `${annotation.label}: ${annotation.side.toUpperCase()} ${annotation.price.toFixed(4)} @ ${clockSeconds(annotation.second)} ET`
      : `${annotation.label}: ${clock(annotation.minute)} ET`).join(' | ');
}

export function entryTitle(entry: Entry): string {
  const boundary = entry.as_of_m == null ? '' : ` | as of ${clock(entry.as_of_m)} ET`;
  return `${entry.symbol} | ${entry.date}${boundary}`;
}

export function contextLabel(entry: Entry): string {
  if (entry.bar_seconds) return `${entry.bar_seconds}-second bars from prints; fills are the caller's marks`;
  return entry.as_of_m == null ? 'Observed session; no as-of boundary'
    : `As of ${clock(entry.as_of_m)} ET; amber shows later or crossing candles`;
}
