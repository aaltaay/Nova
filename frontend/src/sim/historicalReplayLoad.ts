/**
 * The one way the desk loads a historical window, shared by the Historical
 * replay panel and the tab prompt so "Load" means the same thing everywhere:
 * fence pending seeks, select, publish the selection, invalidate every replayed
 * consumer.
 */
import { historicalStatus } from './historicalStatusStore';
import { cancelPendingSimSeek, emitSimClockScrub } from './simClockEvents';
import type { HistoricalSelection, HistoricalWindow } from './historicalTypes';

type ReplayRequest = <T>(key: string, path: string, body?: unknown, failure?: string) => Promise<T | undefined>;

export async function selectHistoricalReplay(
  request: ReplayRequest,
  spec: HistoricalWindow,
): Promise<HistoricalSelection | undefined> {
  cancelPendingSimSeek();
  const selected = await request<HistoricalSelection>('select', '/history/select', spec);
  if (!selected) return undefined;
  const data = historicalStatus.getSnapshot().data;
  historicalStatus.invalidate({ ...data, jobs: Array.isArray(data?.jobs) ? data.jobs : [], selection: selected });
  emitSimClockScrub(); // Selection changes also invalidate the previously replayed symbol.
  return selected;
}
