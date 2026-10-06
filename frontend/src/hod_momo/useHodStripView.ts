/**
 * The one way HOD Momo / Running Up rows are made, for every view of them: the
 * Scanner's strip and the Trader's Focus rail half (operator ask 2026-10-06:
 * "if we update the logic of one of them the other one def need to get
 * updated ... i just asked for compact form"). Same stream, same strategy
 * picks, same batches, same NEW flags; the views differ only in how much of a
 * row they draw.
 */
import { useMemo } from 'react';
import type { HodMomoContextValue } from './HodMomoContext';
import { hodMomoStripGroupWindowSec } from './hodMomoStripConstants';
import { groupStripAlerts, type StripAlertGroup } from './hodMomoStripGroups';
import { stripAlertsForMode } from './hodMomoStripRows';
import type { HodDockMode } from './scannerDockModes';
import { defaultHodMomentumVisibleStrategies } from './scannerPartition';
import type { AlertObject } from './types';
import { useStripNewAlerts } from './useStripNewAlerts';

export type HodAlertList = Extract<HodDockMode, 'hod_momo' | 'running_up'>;

export type HodStripView = {
  /** The list's alerts, newest raised first, after the strategy picks. */
  alerts: AlertObject[];
  /** One row per ticker per batch, newest first. */
  groups: StripAlertGroup[];
  /** Alert identities that arrived while this view was mounted. */
  newIds: ReadonlySet<string>;
  /** Strategy colours from the config, by strategy id. */
  strategyColors: Readonly<Record<number, string>>;
  /** What the list's tab counts: tickers with an alert today. */
  count: number;
};

const NO_ALERTS: AlertObject[] = [];
const NO_NEW_IDS: ReadonlySet<string> = new Set();
const DEFAULT_VISIBLE: ReadonlySet<number> = defaultHodMomentumVisibleStrategies();

/** Pure: the rows a HOD list shows. */
export function hodStripGroups(
  alerts: readonly AlertObject[],
  list: HodAlertList,
  visibleStrategies: ReadonlySet<number>,
  consolidationSec: number | null | undefined,
): { alerts: AlertObject[]; groups: StripAlertGroup[] } {
  const shown = stripAlertsForMode(alerts, list, list === 'hod_momo' ? visibleStrategies : null);
  return { alerts: shown, groups: groupStripAlerts(shown, hodMomoStripGroupWindowSec(consolidationSec)) };
}

/**
 * The rows of `list` from the shared HOD context; null without a context or a
 * list (a hook, so a view that may or may not show a HOD list calls it always).
 */
export function useHodStripView(hod: HodMomoContextValue | null, list: HodAlertList | null): HodStripView | null {
  const streamAlerts = hod?.stream.alerts ?? NO_ALERTS;
  const visible = hod?.visibleStrategies ?? DEFAULT_VISIBLE;
  const consolidationSec = hod?.config.state.master?.consolidation_sec;
  const strategies = hod?.config.state.strategies;
  const replay = hod?.replay ?? null;

  const rows = useMemo(
    () => (list ? hodStripGroups(streamAlerts, list, visible, consolidationSec) : null),
    [streamAlerts, list, visible, consolidationSec],
  );
  // Past alerts at the Sim playhead are never NEW: they arrive as the playhead reaches them.
  const liveNewIds = useStripNewAlerts(replay || !list ? NO_ALERTS : streamAlerts);
  const strategyColors = useMemo(() => {
    const out: Record<number, string> = {};
    for (const [sid, cfg] of Object.entries(strategies ?? {})) out[Number(sid)] = cfg.color;
    return out;
  }, [strategies]);

  const newIds = replay ? NO_NEW_IDS : liveNewIds;
  const count = list === 'running_up' ? hod?.runningUpCount : hod?.hodCount;
  return useMemo(
    () => (hod && rows ? { ...rows, newIds, strategyColors, count: count ?? 0 } : null),
    [hod, rows, newIds, strategyColors, count],
  );
}
