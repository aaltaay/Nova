import type { RawBar } from '../../tickerChartData';

export type AnnotationColor = 'blue' | 'gold' | 'grey' | 'green' | 'red';
export type Annotation =
  | { kind: 'horizontal_line'; price: number; label: string; color?: AnnotationColor }
  | { kind: 'time_marker'; minute: number; label: string; color?: AnnotationColor }
  | { kind: 'trade_marker'; side: 'buy' | 'sell'; second: number; price: number; label: string; color?: AnnotationColor };

/** Sub-minute bar sizes a trade chart may draw (`bar_seconds`); minute entries draw 1Min + 5Min. */
export const SUB_MINUTE_BAR_SECONDS = [1, 5, 10, 15, 30] as const;
export type PaneTimeframe = '1Min' | '5Min' | `${(typeof SUB_MINUTE_BAR_SECONDS)[number]}Sec`;

export interface Entry {
  id: number; symbol: string; date: string; as_of_m?: number; as_of_t?: string;
  annotations: Annotation[]; bars_1m: RawBar[]; bars_5m: RawBar[];
  bar_seconds?: number; bars_sub?: RawBar[];
  source: { selection_sha256: string; projection_sha256: string };
}
export interface Gallery {
  schema_version: 1; kind: 'historical_ohlcv'; family: string; selection_sha256: string;
  entries: Entry[]; timings: { load_ms: number; aggregation_ms: number };
}
