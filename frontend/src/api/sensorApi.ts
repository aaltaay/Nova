import { API_BASE_URL } from '../constantGroups/chart_api';
import { novaFetch } from './novaFetch';
import type { SensorCatalog, SensorEnvelope, SensorSnapshot } from '../sensors/types';

function sensorsUrl(path: string, symbol?: string): string {
  const url = new URL(path, `${API_BASE_URL}/`);
  if (symbol) url.searchParams.set('symbol', symbol);
  return url.toString();
}

export async function fetchSensorCatalog(): Promise<SensorCatalog> {
  const res = await novaFetch(sensorsUrl('/sensors'));
  if (!res.ok) throw new Error(`Sensor catalog HTTP ${res.status}`);
  return res.json() as Promise<SensorCatalog>;
}

export async function fetchSensorSnapshot(symbol: string): Promise<SensorSnapshot> {
  const res = await novaFetch(sensorsUrl('/sensors/snapshot', symbol));
  if (!res.ok) throw new Error(`Sensor snapshot HTTP ${res.status}`);
  return res.json() as Promise<SensorSnapshot>;
}

export async function fetchOneSensor(path: string, symbol?: string): Promise<SensorEnvelope> {
  const res = await novaFetch(sensorsUrl(path, symbol));
  if (!res.ok) throw new Error(`Sensor HTTP ${res.status}`);
  return res.json() as Promise<SensorEnvelope>;
}
