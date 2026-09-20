import { SIM_ET_TIME_ZONE, SIM_HISTORY_SYMBOL_PATTERN } from './simConstants';
import type { HistoricalJob, HistoricalWindow } from './historicalTypes';
export const jobLabel = (job: HistoricalJob) => `${job.symbol} ${job.date} ${job.start} - ${job.end} ${job.kind}`;
export const windowLabel = (spec: HistoricalWindow) => `${spec.symbol}  -  ${spec.date}  -  ${spec.start} - ${spec.end} ET`;
export function progressPercent(job: HistoricalJob): number | null {
  if (job.progress_pct != null) return Math.max(0, Math.min(100, job.progress_pct));
  if (job.start_ts == null || job.end_ts == null || job.cursor == null || job.end_ts <= job.start_ts) return null;
  return Math.max(0, Math.min(100, (job.cursor - job.start_ts) / (job.end_ts - job.start_ts) * 100));
}
export function durationLabel(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.ceil(seconds % 3600 / 60)}m`;
}
export function windowMinutes(spec: HistoricalWindow): number {
  const minutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));
  return minutes(spec.end) - minutes(spec.start);
}
export function validateHistoricalWindow(spec: HistoricalWindow, now = new Date()): string | null {
  if (!SIM_HISTORY_SYMBOL_PATTERN.test(spec.symbol)) return 'Enter a stock ticker';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(spec.date) || !Number.isFinite(Date.parse(`${spec.date}T12:00:00Z`))) return 'Choose a valid session date';
  if (![spec.start, spec.end].every(value => /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value))) return 'Session times must be HH:MM Eastern';
  if (windowMinutes(spec) <= 0) return 'Choose a window with start before end';
  const today = now.toLocaleDateString('en-CA', { timeZone: SIM_ET_TIME_ZONE });
  const time = now.toLocaleTimeString('en-GB', { timeZone: SIM_ET_TIME_ZONE, hour12: false }).slice(0, 5);
  if (spec.date > today || (spec.date === today && spec.end > time)) return 'Choose a completed historical window';
  return null;
}
export function jobSummary(job: HistoricalJob): string {
  const percent = progressPercent(job);
  const status = job.stale ? 'Stalled' : job.status === 'pause_requested' ? 'Pausing' : job.status;
  return `${job.symbol} ${status}${percent == null ? '' : `  -  ${percent.toFixed(0)}%`}`;
}
