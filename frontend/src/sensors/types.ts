export type SensorStatus = 'live' | 'stub' | 'computed_stub';
/** `stale`: a live sensor whose 1-minute bars are old (QA W16). */
export type SensorChipStatus = SensorStatus | 'error' | 'stale';

export interface SensorCatalogRow {
  id: number;
  sensor: string;
  title: string;
  path: string;
  status: SensorStatus;
  needs_symbol: boolean;
}

export interface SensorEnvelope {
  sensor: string;
  title?: string;
  symbol?: string;
  status: SensorStatus;
  as_of: number;
  data: Record<string, unknown>;
  error?: string;
}

export interface SensorSnapshot {
  symbol: string;
  count: number;
  sensors: SensorEnvelope[];
}

export interface SensorCatalog {
  count: number;
  sensors: SensorCatalogRow[];
}
