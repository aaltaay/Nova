/**
 * Focus list rail (approved redesign rev. 2 / 7): a collapsible ~220 px strip
 * between the navigation rail and the charts, split in two halves that each
 * mirror a scanner list (operator ask 2026-09-24: "I wanna see HOD all the
 * time" -- the upper half keeps the rail's list, the lower half shows HOD
 * Momo unless another list is picked, and folds to its header). Each half is
 * a FocusRailPane: header `<list> N ▾` (the caret picks a scanner tab module
 * from the registry), sortable columns, rows of REC dot, bot dot (filled =
 * allowlisted and this desk holds the depth line -- a live Trader tab or a
 * recording; hollow = allowlisted, quiet), symbol, price, signed gap, led by
 * the Scanner's own news circle. ↑ ↓ cycle in the focused half, Enter opens.
 * Opening a symbol from a scanner list (a Gainers row, the HOD strip, the
 * Desk board) moves a half to that list when it mirrors it (routeFocusList).
 * Data is the live scanner feed the workspace already holds -- and, for HOD
 * Momo / Running Up, the HOD stream the app shell keeps open -- without one
 * the half says so.
 */
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from 'lucide-react';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { useWatchList } from '../watch_list';
import { getRecordingSymbols, isTabRecording, subscribeSessionRecord } from '../capture/sessionRecordStore';
import {
  FOCUS_RAIL_ARIA,
  FOCUS_RAIL_COLLAPSE,
  FOCUS_RAIL_EXPAND,
  FOCUS_RAIL_FOOTER_CYCLE,
  FOCUS_RAIL_FOOTER_ENTER,
  FOCUS_RAIL_FOOTER_KEYS,
  FOCUS_RAIL_FOOTER_OPENS,
  FOCUS_RAIL_LOWER_FOLD,
  FOCUS_RAIL_LOWER_PICK_ARIA,
  FOCUS_RAIL_LOWER_UNFOLD,
  FOCUS_RAIL_NO_FEED,
  FOCUS_RAIL_PICK_ARIA,
  FOCUS_RAIL_TITLE,
  FOCUS_RAIL_WATCH_EMPTY,
  focusRailEmpty,
  focusRailNotMirrored,
} from '../constantGroups/trader_chrome';
import { listFeedFailed } from '../constantGroups/scanner_board';
import { useHodMomoOptional, type HodMomoContextValue } from '../hod_momo/HodMomoContext';
import { HOD_MOMO_STRIP_EMPTY_CONNECTING } from '../hod_momo/hodMomoStripConstants';
import { useLiveScannerFeedOptional, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import { listAbsenceText } from '../scanner/listAbsence';
import { replayListAbsence } from '../leaderboard/leaderboardRows';
import { useSettingsOptional } from '../settings/SettingsContext';
import { useSimReplayDesk } from '../sim/useSimReplayDesk';
import { consumeFocusListRequest, subscribeFocusListRequest } from '../workspace';
import {
  isTabModuleId, listScannerListModules, tabUsesScannerPricePatch, type ActiveTab, type NovaModule,
} from '../workspace/registry';
import { useWorkspace } from '../workspace/WorkspaceContext';
import type { ScannerRow } from '../types/scanner';
import {
  SAVED_FOCUS_RAIL_STORE, focusRowsFor, hodFocusRows, isHodFocusList, routeFocusList, watchFocusRows,
  FOCUS_RAIL_WATCH_LIST, type FocusPaneState, type FocusRailState, type FocusRailStore, type FocusRow,
} from './focusRailState';
import { FocusRailPane, type FocusPaneShared, type FocusPaneView } from './FocusRailPane';
import { sortFocusRows, type FocusSort } from './focusRailSort';
import './focusRail.css';

type HodStream = HodMomoContextValue['stream'];

/** What the rail reads to build a half's rows. */
interface FocusSources {
  feed: LiveScannerFeed | null;
  hodStream: HodStream | null;
  filterRows?: <T extends ScannerRow>(rows: T[]) => T[];
  watchList: readonly string[];
}

/** A list's rows in its own order; null when this desk does not carry it. */
function listRows(list: string, src: FocusSources): FocusRow[] | null {
  const { feed, hodStream, filterRows, watchList } = src;
  if (isHodFocusList(list)) return hodStream ? hodFocusRows(list, hodStream.alerts, feed) : null;
  if (list === FOCUS_RAIL_WATCH_LIST) return watchFocusRows(watchList, feed);
  return focusRowsFor(list, feed, filterRows);
}

/** What an empty or missing list says. The HOD lists answer from their own
 * stream (failed / connecting / empty), the rest from the scanner feed. */
function absenceText(title: string, list: string, rows: FocusRow[] | null, src: FocusSources): string {
  const { feed, hodStream } = src;
  if (isHodFocusList(list)) {
    if (!hodStream) return focusRailNotMirrored(title);
    if (hodStream.feedError) return listFeedFailed(title, hodStream.feedError);
    return hodStream.connected ? focusRailEmpty(title) : HOD_MOMO_STRIP_EMPTY_CONNECTING;
  }
  // The watch list is the operator's own: empty means nothing picked, whatever the feed says.
  if (list === FOCUS_RAIL_WATCH_LIST) return FOCUS_RAIL_WATCH_EMPTY;
  if (!feed) return FOCUS_RAIL_NO_FEED;
  if (rows == null) return focusRailNotMirrored(title);
  // The feed follows the Sim playhead (ADR 023): its absence is the playhead's.
  if (feed.replay) return replayListAbsence(feed.replay, list);
  return listAbsenceText(title, { restError: feed.restError, healthStatus: feed.health?.status }, focusRailEmpty);
}

/** One half's view. Off the live edge only the symbol sort applies: ordering
 * by today's price, % or news would show what the rows hide (QA W10). */
function paneView(pane: FocusPaneState, src: FocusSources, replayDesk: boolean, modules: readonly NovaModule[]): FocusPaneView {
  const title = (modules.find(m => m.id === pane.list) ?? modules[0])?.title ?? pane.list;
  const sort = replayDesk && pane.sort?.key !== 'symbol' ? null : pane.sort;
  const listed = listRows(pane.list, src);
  const rows = listed ? sortFocusRows(listed, sort) : null;
  return { list: pane.list, title, rows, absent: absenceText(title, pane.list, rows, src), sort };
}

export function FocusRail({ active: onScreen = true, store = SAVED_FOCUS_RAIL_STORE }: {
  active?: boolean;
  /** Where the lists, sorts and folds live (the sample desk passes its own, #449). */
  store?: FocusRailStore;
} = {}) {
  const feed = useLiveScannerFeedOptional();
  const hodStream = useHodMomoOptional()?.stream ?? null;
  const settings = useSettingsOptional();
  const { activeTraderSymbol, traderLiveTabs, openStockView } = useWorkspace();
  const { isAllowed } = useBotAllowlist();
  const watchList = useWatchList();
  // Sim off the live edge replays another moment: today's live price, gap and
  // news stay off the rows; the list still opens tabs (QA W10). A feed that
  // follows the playhead (ADR 023) is that moment's, so its values show.
  const replayDesk = useSimReplayDesk() && !feed?.replay;
  useSyncExternalStore(subscribeSessionRecord, () => getRecordingSymbols().join(','), () => '');
  const [state, setState] = useState<FocusRailState>(() => store.read());
  const modules = useMemo(() => listScannerListModules(), []);

  const update = useCallback((patch: Partial<FocusRailState>) => {
    setState(prev => {
      const next = { ...prev, ...patch };
      store.write(next);
      return next;
    });
  }, [store]);
  const pickUpper = useCallback((list: string) => update({ list }), [update]);
  const sortUpper = useCallback((sort: FocusSort | null) => update({ sort }), [update]);
  const updateLower = useCallback((patch: Partial<FocusRailState['lower']>) => {
    setState(prev => {
      const next = { ...prev, lower: { ...prev.lower, ...patch } };
      store.write(next);
      return next;
    });
  }, [store]);
  const pickLower = useCallback((list: string) => updateLower({ list }), [updateLower]);
  const sortLower = useCallback((sort: FocusSort | null) => updateLower({ sort }), [updateLower]);

  // Follow the list the last symbol was picked from; the request may predate this mount.
  useEffect(() => {
    const follow = () => {
      const requested = consumeFocusListRequest();
      setState(prev => {
        const patch = routeFocusList(prev, requested);
        if (!patch) return prev;
        const next = { ...prev, ...patch };
        store.write(next);
        return next;
      });
    };
    follow();
    return subscribeFocusListRequest(follow);
  }, [store]);

  // Declare the mirrored lists for IBKR L1 (ADR 008) while their rows are on
  // screen: an undeclared table gets no price patches, so a Large Cap rail
  // beside a Scanner left on Gappers showed a dash for every price.
  const setL1FocusTabs = feed?.setL1FocusTabs;
  const shown = onScreen && !state.collapsed;
  // Only a table that takes price patches is declared (HOD Momo / Running Up are alert lists).
  const upperTab = shown && declares(state.list) ? state.list : null;
  const lowerTab = shown && !state.lower.folded && declares(state.lower.list) ? state.lower.list : null;
  const focusKey = [...new Set([upperTab, lowerTab].filter((t): t is ActiveTab => t != null))].join(',');
  useEffect(() => {
    setL1FocusTabs?.(focusKey ? (focusKey.split(',') as ActiveTab[]) : []);
  }, [focusKey, setL1FocusTabs]);
  useEffect(() => () => setL1FocusTabs?.([]), [setL1FocusTabs]);

  const filterRows = settings?.exchangeFilter?.filterRows;
  const src = useMemo<FocusSources>(() => ({ feed, hodStream, filterRows, watchList }),
    [feed, hodStream, filterRows, watchList]);
  const upperPane = useMemo<FocusPaneState>(() => ({ list: state.list, sort: state.sort }), [state.list, state.sort]);
  const upper = useMemo(() => paneView(upperPane, src, replayDesk, modules), [upperPane, src, replayDesk, modules]);
  const lower = useMemo(() => paneView(state.lower, src, replayDesk, modules), [state.lower, src, replayDesk, modules]);
  const shared = useMemo<FocusPaneShared>(() => ({
    replayDesk,
    watchList,
    isAllowed,
    isRecording: isTabRecording,
    active: activeTraderSymbol?.toUpperCase() ?? null,
    traderLiveTabs,
    open: (symbol: string) => openStockView(symbol),
    modules,
  }), [replayDesk, watchList, isAllowed, activeTraderSymbol, traderLiveTabs, openStockView, modules]);

  if (state.collapsed) {
    const count = upper.rows?.length ?? null;
    return (
      <aside className="focus-rail focus-rail--collapsed" aria-label={FOCUS_RAIL_ARIA} data-testid="focus-rail" data-collapsed="1">
        <button type="button" className="focus-rail__expand" aria-label={FOCUS_RAIL_EXPAND} title={FOCUS_RAIL_EXPAND}
          data-testid="focus-rail-expand" onClick={() => update({ collapsed: false })}>
          <ChevronRight size={14} aria-hidden="true" />
          <span className="focus-rail__vertical">{FOCUS_RAIL_TITLE}{count != null ? ` · ${count}` : ''}</span>
        </button>
      </aside>
    );
  }

  const folded = state.lower.folded;
  const FoldIcon = folded ? ChevronUp : ChevronDown;
  return (
    <aside className="focus-rail" aria-label={FOCUS_RAIL_ARIA} data-testid="focus-rail" data-split={folded ? '0' : '1'}>
      <FocusRailPane
        tid="focus-rail" half="upper" view={upper} onPick={pickUpper} onSort={sortUpper} shared={shared}
        title={FOCUS_RAIL_TITLE} pickAria={FOCUS_RAIL_PICK_ARIA}
        control={(
          <button type="button" className="focus-rail__collapse" aria-label={FOCUS_RAIL_COLLAPSE} title={FOCUS_RAIL_COLLAPSE}
            data-testid="focus-rail-collapse" onClick={() => update({ collapsed: true })}>
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
        )}
      />
      <FocusRailPane
        tid="focus-rail-lower" half="lower" view={lower} onPick={pickLower} onSort={sortLower} shared={shared}
        pickAria={FOCUS_RAIL_LOWER_PICK_ARIA} folded={folded}
        control={(
          <button type="button" className="focus-rail__collapse"
            aria-label={folded ? FOCUS_RAIL_LOWER_UNFOLD : FOCUS_RAIL_LOWER_FOLD}
            title={folded ? FOCUS_RAIL_LOWER_UNFOLD : FOCUS_RAIL_LOWER_FOLD} aria-expanded={!folded}
            data-testid="focus-rail-lower-fold" onClick={() => updateLower({ folded: !folded })}>
            <FoldIcon size={14} aria-hidden="true" />
          </button>
        )}
      />
      <div className="focus-rail__foot">
        <b>{FOCUS_RAIL_FOOTER_KEYS}</b> {FOCUS_RAIL_FOOTER_CYCLE} <b>{FOCUS_RAIL_FOOTER_ENTER}</b> {FOCUS_RAIL_FOOTER_OPENS}
      </div>
    </aside>
  );
}

function declares(list: string): list is ActiveTab {
  return isTabModuleId(list) && tabUsesScannerPricePatch(list);
}
