import type { RawBar } from '../../tickerChartData';

export type AnnotationColor = 'blue' | 'gold' | 'grey' | 'green' | 'red';
export type Annotation =
  | { kind: 'horizontal_line'; price: number; label: string; color?: AnnotationColor }
  | { kind: 'time_marker'; minute: number; label: string; color?: AnnotationColor };

export interface Entry {
  id: number; symbol: string; date: string; as_of_m?: number; as_of_t?: string;
  annotations: Annotation[]; bars_1m: RawBar[]; bars_5m: RawBar[];
  source: { selection_sha256: string; projection_sha256: string };
}
export interface Gallery {
  schema_version: 1; kind: 'historical_ohlcv'; family: string; selection_sha256: string;
  entries: Entry[]; timings: { load_ms: number; aggregation_ms: number };
}
