import type { Annotation, AnnotationColor, Entry } from './types';

/** Fixed public palette; annotation inputs never become arbitrary CSS. */
export const ANNOTATION_COLORS: Record<AnnotationColor, string> = {
  blue: '#4da8ff', gold: '#e5b45b', grey: '#a2aab8', green: '#10b981', red: '#ef4444',
};
export const clock = (minute: number) => `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;

export function annotationColor(color: AnnotationColor = 'blue'): string {
  if (!Object.hasOwn(ANNOTATION_COLORS, color)) throw new Error('Invalid annotation color');
  return ANNOTATION_COLORS[color];
}

export function priceLineOptions(annotations: Annotation[]) {
  return annotations.filter(annotation => annotation.kind === 'horizontal_line').map(annotation => ({
    price: annotation.price, title: annotation.label, color: annotationColor(annotation.color), lineWidth: 1 as const,
  }));
}

export function annotationSummary(annotations: Annotation[]): string {
  return annotations.map(annotation => annotation.kind === 'horizontal_line'
    ? `${annotation.label}: ${annotation.price.toFixed(4)}`
    : `${annotation.label}: ${clock(annotation.minute)} ET`).join(' | ');
}

export function entryTitle(entry: Entry): string {
  const boundary = entry.as_of_m == null ? '' : ` | as of ${clock(entry.as_of_m)} ET`;
  return `${entry.symbol} | ${entry.date}${boundary}`;
}

export function contextLabel(entry: Entry): string {
  return entry.as_of_m == null ? 'Observed session; no as-of boundary'
    : `As of ${clock(entry.as_of_m)} ET; amber shows later or crossing candles`;
}
