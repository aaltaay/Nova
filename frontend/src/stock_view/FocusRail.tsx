/**
 * Focus list rail (approved redesign rev. 2 / 7): a collapsible ~220 px strip
 * between the navigation rail and the charts that mirrors any scanner list.
 * Header `FOCUS · <list> N ▾` (the caret picks a scanner tab module from the
 * registry), collapse chevron (the rail already leads to the Scanner). Rows: REC dot, bot dot (filled
 * = allowlisted and this desk holds the depth line -- a live Trader tab or a
 * recording; hollow = allowlisted, quiet), symbol, price, signed gap. The
 * first column is the Scanner's own news circle (NewsCell: red / orange /
 * yellow by age, the verdict's ring, ! and H marks); blank when unknown.
 * Hovering the circle opens the symbol's news beside the rail, hovering the
 * REC / bot dots says what they mean; leaving the row closes the card. The column headers sort the list (click, flip, third
 * click back to the list's own order), remembered with the list. ↑ ↓ cycle
 * in the order shown, Enter opens. Opening a symbol from a
 * scanner list (a Gainers row, the HOD strip, the Desk board) moves the rail
 * to that list when it mirrors it. Data is the live scanner feed
 * the workspace already holds -- and, for HOD Momo / Running Up, the HOD
 * stream the app shell keeps open -- without one the rail says so.
 */
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { NewsCell } from '../components/NewsCell';
import { getRecordingSymbols, isTabRecording, subscribeSessionRecord } from '../capture/sessionRecordStore';
import {
  FOCUS_RAIL_ARIA,
  FOCUS_RAIL_BOT_HELD_TITLE,
  FOCUS_RAIL_BOT_QUIET_TITLE,
  FOCUS_RAIL_CARD_HIDE_MS,
  FOCUS_RAIL_COLLAPSE,
  FOCUS_RAIL_EXPAND,
  FOCUS_RAIL_FOOTER_CYCLE,
  FOCUS_RAIL_FOOTER_ENTER,
  FOCUS_RAIL_FOOTER_KEYS,
  FOCUS_RAIL_FOOTER_OPENS,
  FOCUS_RAIL_NO_FEED,
  FOCUS_RAIL_PICK_ARIA,
  FOCUS_RAIL_REC_TITLE,
  FOCUS_RAIL_SORT_LABELS,
  FOCUS_RAIL_SORT_RESET,
  FOCUS_RAIL_SORT_TITLES,
  FOCUS_RAIL_TITLE,
  focusRailEmpty,
  focusRailNotMirrored,
} from '../constantGroups/trader_chrome';
import { listFeedFailed } from '../constantGroups/scanner_board';
import { useHodMomoOptional, type HodMomoContextValue } from '../hod_momo/HodMomoContext';
import { HOD_MOMO_STRIP_EMPTY_CONNECTING } from '../hod_momo/hodMomoStripConstants';
import { useLiveScannerFeedOptional, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import { listAbsenceText } from '../scanner/listAbsence';
import { replayListAbsence } from '../leaderboard/leaderboardRows';
import { TRADER_TAB_GAP_TITLE } from '../constantGroups/trader_view';
import { useSettingsOptional } from '../settings/SettingsContext';
import { SIM_FOCUS_RAIL_REPLAY_NOTE } from '../sim/simConstants';
import { useSimReplayDesk } from '../sim/useSimReplayDesk';
import { consumeFocusListRequest, subscribeFocusListRequest } from '../workspace';
import { isTabModuleId, listScannerListModules } from '../workspace/registry';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  followedFocusList, focusRowsFor, hodFocusRows, isHodFocusList, readFocusRailState, stepCursor, writeFocusRailState,
  type FocusRailState, type FocusRow,
} from './focusRailState';
import { FocusRailHoverCard, type FocusRailHover } from './FocusRailHoverCard';
import { nextFocusSort, sortFocusRows, type FocusSort, type FocusSortKey } from './focusRailSort';
import { formatSignedPct, pctTone } from './tabContext';
import './focusRail.css';

type HodStream = HodMomoContextValue['stream'];

/** What an empty or missing list says. The HOD lists answer from their own
 * stream (failed / connecting / empty), the rest from the scanner feed. */
function absenceText(
  title: string,
  hodList: boolean,
  hodStream: HodStream | null,
  feed: LiveScannerFeed | null,
  rows: FocusRow[] | null,
  list: string,
): string {
  if (hodList) {
    if (!hodStream) return focusRailNotMirrored(title);
    if (hodStream.feedError) return listFeedFailed(title, hodStream.feedError);
    return hodStream.connected ? focusRailEmpty(title) : HOD_MOMO_STRIP_EMPTY_CONNECTING;
  }
  if (!feed) return FOCUS_RAIL_NO_FEED;
  if (rows == null) return focusRailNotMirrored(title);
  // The feed follows the Sim playhead (ADR 023): its absence is the playhead's.
  if (feed.replay) return replayListAbsence(feed.replay, list);
  return listAbsenceText(title, { restError: feed.restError, healthStatus: feed.health?.status }, focusRailEmpty);
}

/** One sortable column header; the active one shows its direction. */
function SortHeader({ column, sort, onSort }: { column: FocusSortKey; sort: FocusSort | null; onSort: (key: FocusSortKey) => void }) {
  const on = sort?.key === column ? sort.dir : null;
  const Arrow = on === 'asc' ? ArrowUp : ArrowDown;
  return (
    <button type="button" className={`focus-rail__th focus-rail__th--${column}${on ? ' is-sorted' : ''}`}
      aria-sort={on === 'asc' ? 'ascending' : on === 'desc' ? 'descending' : 'none'}
      title={on ? `${FOCUS_RAIL_SORT_TITLES[column]} · ${FOCUS_RAIL_SORT_RESET}` : FOCUS_RAIL_SORT_TITLES[column]}
      data-testid={`focus-rail-sort-${column}`} data-dir={on ?? ''} onClick={() => onSort(column)}>
      {FOCUS_RAIL_SORT_LABELS[column]}
      {on && <Arrow size={9} aria-hidden="true" />}
    </button>
  );
}

export function FocusRail({ active: onScreen = true }: { active?: boolean } = {}) {
  const feed = useLiveScannerFeedOptional();
  const hodStream = useHodMomoOptional()?.stream ?? null;
  const settings = useSettingsOptional();
  const { activeTraderSymbol, traderLiveTabs, openStockView } = useWorkspace();
  const { isAllowed } = useBotAllowlist();
  // Sim off the live edge replays another moment: today's live price, gap and
  // news stay off the rows; the list still opens tabs (QA W10). A feed that
  // follows the playhead (ADR 023) is that moment's, so its values show.
  const replayDesk = useSimReplayDesk() && !feed?.replay;
  useSyncExternalStore(subscribeSessionRecord, () => getRecordingSymbols().join(','), () => '');
  const [state, setState] = useState<FocusRailState>(readFocusRailState);
  const [cursor, setCursor] = useState(-1);
  const [hover, setHover] = useState<FocusRailHover | null>(null);
  const hideTimer = useRef<number | null>(null);
  const modules = useMemo(() => listScannerListModules(), []);
  const module = modules.find(m => m.id === state.list) ?? modules[0];
  const filterRows = settings?.exchangeFilter?.filterRows;
  const hodList = isHodFocusList(state.list);
  const hodAlerts = hodStream?.alerts;
  // Off the live edge only the symbol sort applies: ordering by today's
  // price, % or news would show what the rows hide (QA W10).
  const sort = replayDesk && state.sort?.key !== 'symbol' ? null : state.sort;
  const rows = useMemo(() => {
    const listed = isHodFocusList(state.list)
      ? (hodAlerts ? hodFocusRows(state.list, hodAlerts, feed) : null)
      : focusRowsFor(state.list, feed, filterRows);
    return listed ? sortFocusRows(listed, sort) : null;
  }, [state.list, feed, filterRows, hodAlerts, sort]);
  const title = module?.title ?? state.list;
  const absent = absenceText(title, hodList, hodStream, feed, rows, state.list);

  const keepCard = useCallback(() => {
    if (hideTimer.current != null) window.clearTimeout(hideTimer.current);
    hideTimer.current = null;
  }, []);
  // A short grace, so the pointer can cross the row into the card.
  const hideCard = useCallback(() => {
    keepCard();
    hideTimer.current = window.setTimeout(() => { hideTimer.current = null; setHover(null); }, FOCUS_RAIL_CARD_HIDE_MS);
  }, [keepCard]);
  useEffect(() => keepCard, [keepCard]);
  const showCard = (target: HTMLElement, card: Omit<FocusRailHover, 'anchor'>) => {
    keepCard();
    const r = (target.closest('.focus-rail__row') ?? target).getBoundingClientRect();
    setHover({ ...card, anchor: { left: r.left, top: r.top, right: r.right, bottom: r.bottom } });
  };

  const update = useCallback((patch: Partial<FocusRailState>) => {
    setState(prev => {
      const next = { ...prev, ...patch };
      writeFocusRailState(next);
      return next;
    });
  }, []);

  // Follow the list the last symbol was picked from; the request may predate this mount.
  useEffect(() => {
    const follow = () => {
      const list = followedFocusList(consumeFocusListRequest());
      if (list) update({ list });
    };
    follow();
    return subscribeFocusListRequest(follow);
  }, [update]);

  useEffect(() => { setCursor(-1); setHover(null); }, [state.list, sort?.key, sort?.dir]);
  const onSort = (key: FocusSortKey) => update({ sort: nextFocusSort(sort, key) });

  // Declare the mirrored list for IBKR L1 (ADR 008) while its rows are on
  // screen: an undeclared table gets no price patches, so a Large Cap rail
  // beside a Scanner left on Gappers showed a dash for every price.
  const setL1FocusTab = feed?.setL1FocusTab;
  const focusTab = onScreen && !state.collapsed && isTabModuleId(state.list) ? state.list : null;
  useEffect(() => {
    setL1FocusTab?.(focusTab);
  }, [focusTab, setL1FocusTab]);
  useEffect(() => () => setL1FocusTab?.(null), [setL1FocusTab]);

  const open = (symbol: string) => openStockView(symbol);
  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!rows?.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor(current => stepCursor(current, event.key === 'ArrowDown' ? 1 : -1, rows.length));
    } else if (event.key === 'Enter' && cursor >= 0 && rows[cursor]) {
      event.preventDefault();
      open(rows[cursor].symbol);
    }
  };

  if (state.collapsed) {
    return (
      <aside className="focus-rail focus-rail--collapsed" aria-label={FOCUS_RAIL_ARIA} data-testid="focus-rail" data-collapsed="1">
        <button type="button" className="focus-rail__expand" aria-label={FOCUS_RAIL_EXPAND} title={FOCUS_RAIL_EXPAND}
          data-testid="focus-rail-expand" onClick={() => update({ collapsed: false })}>
          <ChevronRight size={14} aria-hidden="true" />
          <span className="focus-rail__vertical">{FOCUS_RAIL_TITLE}{rows ? ` · ${rows.length}` : ''}</span>
        </button>
      </aside>
    );
  }

  const active = activeTraderSymbol?.toUpperCase() ?? null;
  return (
    <aside className="focus-rail" aria-label={FOCUS_RAIL_ARIA} data-testid="focus-rail" tabIndex={0} onKeyDown={onKeyDown}>
      <div className="focus-rail__head">
        <label className="focus-rail__src" title={FOCUS_RAIL_PICK_ARIA}>
          <span className="focus-rail__title">{FOCUS_RAIL_TITLE}</span>
          <span className="focus-rail__list" data-testid="focus-rail-list-label">· {module?.title ?? state.list}{rows ? ` ${rows.length}` : ''}</span>
          <ChevronDown size={10} aria-hidden="true" />
          <select className="focus-rail__pick" aria-label={FOCUS_RAIL_PICK_ARIA} data-testid="focus-rail-pick"
            value={state.list} onChange={event => update({ list: event.target.value })}>
            {modules.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
        </label>
        <button type="button" className="focus-rail__collapse" aria-label={FOCUS_RAIL_COLLAPSE} title={FOCUS_RAIL_COLLAPSE}
          data-testid="focus-rail-collapse" onClick={() => update({ collapsed: true })}>
          <ChevronLeft size={14} aria-hidden="true" />
        </button>
      </div>
      {rows != null && rows.length > 0 && (
        <div className="focus-rail__cols" data-testid="focus-rail-cols">
          {replayDesk ? <span className="focus-rail__news" /> : <SortHeader column="news" sort={sort} onSort={onSort} />}
          <span className="focus-rail__dots" />
          <SortHeader column="symbol" sort={sort} onSort={onSort} />
          {!replayDesk && (
            <>
              <SortHeader column="price" sort={sort} onSort={onSort} />
              <SortHeader column="gap" sort={sort} onSort={onSort} />
            </>
          )}
        </div>
      )}
      <div className="focus-rail__rows" role="listbox" aria-label={module?.title ?? state.list} data-testid="focus-rail-rows"
        onScroll={() => setHover(null)}>
        {replayDesk && rows != null && rows.length > 0 && (
          <p className="focus-rail__absent" data-testid="focus-rail-replay-note">{SIM_FOCUS_RAIL_REPLAY_NOTE}</p>
        )}
        {rows == null || rows.length === 0 ? (
          <p className="focus-rail__absent" data-testid="focus-rail-absent">{absent}</p>
        ) : rows.map((row, index) => {
          const recording = isTabRecording(row.symbol);
          const allowed = isAllowed(row.symbol);
          const held = allowed && (recording || traderLiveTabs.includes(row.symbol));
          const isActive = row.symbol === active;
          const flags = { row, recording, allowed, held };
          return (
            <div
              key={row.symbol}
              role="option"
              aria-selected={isActive}
              className={`focus-rail__row${isActive ? ' is-active' : ''}${index === cursor ? ' is-cursor' : ''}`}
              data-testid={`focus-rail-row-${row.symbol}`}
              onClick={() => { setCursor(index); open(row.symbol); }}
              onMouseEnter={() => { if (hover?.row.symbol === row.symbol) keepCard(); }}
              onMouseLeave={hideCard}
            >
              <span className="focus-rail__news" data-testid={`focus-rail-news-${row.symbol}`}
                onMouseEnter={replayDesk ? undefined : event => showCard(event.currentTarget, { kind: 'news', ...flags })}>
                {!replayDesk && row.newsKnown && <NewsCell newest_headline_at={row.headlineAt} catalyst={row.verdict} plain />}
              </span>
              <span className="focus-rail__dots" data-testid={`focus-rail-dots-${row.symbol}`}
                onMouseEnter={recording || allowed ? event => showCard(event.currentTarget, { kind: 'status', ...flags }) : undefined}>
                {recording && <i className="focus-rail__dot focus-rail__dot--rec" aria-label={FOCUS_RAIL_REC_TITLE} data-testid={`focus-rail-rec-${row.symbol}`} />}
                {allowed && (
                  <i className={`focus-rail__dot focus-rail__dot--bot${held ? '' : ' focus-rail__dot--quiet'}`}
                    aria-label={held ? FOCUS_RAIL_BOT_HELD_TITLE : FOCUS_RAIL_BOT_QUIET_TITLE}
                    data-testid={`focus-rail-bot-${row.symbol}`} data-held={held ? '1' : '0'} />
                )}
              </span>
              <span className="focus-rail__sym">{row.symbol}</span>
              {!replayDesk && (
                <>
                  <span className="focus-rail__px">{row.price != null ? row.price.toFixed(2) : '—'}</span>
                  <span className={`focus-rail__gap focus-rail__gap--${pctTone(row.gapPct)}`} title={TRADER_TAB_GAP_TITLE}>
                    {formatSignedPct(row.gapPct)}
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>
      {hover && <FocusRailHoverCard hover={hover} onEnter={keepCard} onLeave={hideCard} />}
      <div className="focus-rail__foot">
        <b>{FOCUS_RAIL_FOOTER_KEYS}</b> {FOCUS_RAIL_FOOTER_CYCLE} <b>{FOCUS_RAIL_FOOTER_ENTER}</b> {FOCUS_RAIL_FOOTER_OPENS}
      </div>
    </aside>
  );
}
