import { SENSORS_NO_VALUE } from '../constantGroups/sensors';
import type { SensorEnvelope } from './types';

function num(value: unknown, digits = 2): string | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return value.toFixed(digits);
}

function printCount(data: Record<string, unknown>): string | null {
  if (typeof data.print_count !== 'number' || Number.isNaN(data.print_count)) return null;
  return `${data.print_count} prints`;
}

function newsSourceLabel(raw: unknown): string {
  const source = typeof raw === 'string' ? raw.trim() : '';
  if (!source) return 'Advice';
  return source.toLowerCase() === 'advice' ? 'Advice' : source;
}

function newsSummary(data: Record<string, unknown>): string {
  const source = newsSourceLabel(data.source);
  const text =
    (typeof data.headline === 'string' && data.headline.trim()) ||
    (typeof data.sentiment === 'string' && data.sentiment.trim()) ||
    SENSORS_NO_VALUE;
  return `${source} · ${text}`;
}

export function sensorSummary(row: SensorEnvelope): string {
  if (row.error) return row.error;
  const data = row.data || {};
  switch (row.sensor) {
    case 'l2':
      return `imb ${num(data.imbalance, 2) ?? '-'} · spr ${num(data.spread_ticks, 1) ?? '-'}t`;
    case 'tape':
      return printCount(data) ?? SENSORS_NO_VALUE;
    case 'vwap':
      return data.vwap != null ? `VWAP ${num(data.vwap, 3)} (${num(data.distance_ticks, 1) ?? '-'}t)` : SENSORS_NO_VALUE;
    case 'macd':
      return data.ready ? `MACD ${num(data.macd, 3)} / hist ${num(data.histogram, 3)}` : SENSORS_NO_VALUE;
    case 'rvol':
      return data.rvol_vs_adv_pace != null ? `pace ${num(data.rvol_vs_adv_pace, 2)}` : SENSORS_NO_VALUE;
    case 'day-volume':
      return data.day_volume != null ? String(data.day_volume) : SENSORS_NO_VALUE;
    case 'spread':
      return `${num(data.spread_ticks, 1) ?? '-'}t ${data.direction ?? ''}`.trim();
    case 'session-phase':
      return String(data.phase ?? SENSORS_NO_VALUE);
    case 'flow':
      if (data.sweep && typeof data.sweep === 'object') return 'sweep yes';
      return printCount(data) ?? SENSORS_NO_VALUE;
    case 'last-move':
      return data.seconds_ago != null ? `${num(data.seconds_ago, 0)}s ago` : SENSORS_NO_VALUE;
    case 'liquidity':
      return data.adv != null ? `ADV ${data.adv}` : SENSORS_NO_VALUE;
    case 'emas': {
      const e9 = data.ema_9 as { value?: number } | undefined;
      return e9?.value != null ? `EMA9 ${num(e9.value, 3)}` : SENSORS_NO_VALUE;
    }
    case 'news':
      return newsSummary(data);
    case 'risk':
      return `remain ${num(data.daily_loss_limit_remaining, 0)} · L${data.consecutive_losses ?? 0}`;
    case 'halt':
      return data.halted ? `HALT ${data.kind ?? ''}`.trim() : 'not halted';
    case 'memory':
      return `${data.count ?? 0} decisions`;
    case 'regime':
      return `${data.regime ?? 'unknown'} (${num(data.confidence, 2) ?? '-'})`;
    case 'macro':
      return `${data.count ?? 0} stub events`;
    default:
      return SENSORS_NO_VALUE;
  }
}
