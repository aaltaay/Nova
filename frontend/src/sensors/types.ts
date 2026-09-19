export type SensorStatus = 'live' | 'stub' | 'computed_stub';

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
