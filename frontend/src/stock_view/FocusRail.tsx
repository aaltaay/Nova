/**
 * Focus list rail (approved redesign rev. 2 / 7): a collapsible ~220 px strip
 * between the navigation rail and the charts that mirrors any scanner list.
 * Header `FOCUS · <list> N ▾` (the caret picks a scanner tab module from the
 * registry), collapse chevron (the rail already leads to the Scanner). Rows: REC dot, bot dot (filled
 * = allowlisted and this desk holds the depth line -- a live Trader tab or a
 * recording; hollow = allowlisted, quiet), symbol, price, signed gap, catalyst
 * chip or `no news`. ↑ ↓ cycle, Enter opens. Data is the live scanner feed
 * the workspace already holds -- and, for HOD Momo / Running Up, the HOD
 * stream the app shell keeps open -- without one the rail says so.
 */
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { getRecordingSymbols, isTabRecording, subscribeSessionRecord } from '../capture/sessionRecordStore';
import {
  FOCUS_RAIL_ARIA,
  FOCUS_RAIL_BOT_HELD_TITLE,
  FOCUS_RAIL_BOT_QUIET_TITLE,
  FOCUS_RAIL_COLLAPSE,
  FOCUS_RAIL_EXPAND,
  FOCUS_RAIL_FOOTER_CYCLE,
  FOCUS_RAIL_FOOTER_ENTER,
  FOCUS_RAIL_FOOTER_KEYS,
  FOCUS_RAIL_FOOTER_OPENS,
  FOCUS_RAIL_NO_FEED,
  FOCUS_RAIL_PICK_ARIA,
  FOCUS_RAIL_REC_TITLE,
  FOCUS_RAIL_TITLE,
  TRADER_CATALYST_NONE,
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
import { listScannerListModules } from '../workspace/registry';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  focusRowsFor, hodFocusRows, isHodFocusList, readFocusRailState, stepCursor, writeFocusRailState,
  type FocusRailState, type FocusRow,
} from './focusRailState';
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

export function FocusRail() {
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
  const modules = useMemo(() => listScannerListModules(), []);
  const module = modules.find(m => m.id === state.list) ?? modules[0];
  const filterRows = settings?.exchangeFilter?.filterRows;
  const hodList = isHodFocusList(state.list);
  const hodAlerts = hodStream?.alerts;
  const rows = useMemo(() => {
    if (!isHodFocusList(state.list)) return focusRowsFor(state.list, feed, filterRows);
    return hodAlerts ? hodFocusRows(state.list, hodAlerts, feed) : null;
  }, [state.list, feed, filterRows, hodAlerts]);
  const title = module?.title ?? state.list;
  const absent = absenceText(title, hodList, hodStream, feed, rows, state.list);

  const update = useCallback((patch: Partial<FocusRailState>) => {
    setState(prev => {
      const next = { ...prev, ...patch };
      writeFocusRailState(next);
      return next;
    });
  }, []);

  useEffect(() => { setCursor(-1); }, [state.list]);

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
      <div className="focus-rail__rows" role="listbox" aria-label={module?.title ?? state.list} data-testid="focus-rail-rows">
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
          return (
            <div
              key={row.symbol}
              role="option"
              aria-selected={isActive}
              className={`focus-rail__row${isActive ? ' is-active' : ''}${index === cursor ? ' is-cursor' : ''}`}
              data-testid={`focus-rail-row-${row.symbol}`}
              onClick={() => { setCursor(index); open(row.symbol); }}
            >
              <span className="focus-rail__dots">
                {recording && <i className="focus-rail__dot focus-rail__dot--rec" title={FOCUS_RAIL_REC_TITLE} data-testid={`focus-rail-rec-${row.symbol}`} />}
                {allowed && (
                  <i className={`focus-rail__dot focus-rail__dot--bot${held ? '' : ' focus-rail__dot--quiet'}`}
                    title={held ? FOCUS_RAIL_BOT_HELD_TITLE : FOCUS_RAIL_BOT_QUIET_TITLE}
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
                  {row.catalyst ? (
                    <span className="focus-rail__chip" title={row.headline ? `${row.catalyst} · ${row.headline}` : row.catalyst}>{row.catalyst}</span>
                  ) : row.newsKnown ? (
                    <span className="focus-rail__chip focus-rail__chip--none">{TRADER_CATALYST_NONE}</span>
                  ) : null}
                </>
              )}
            </div>
          );
        })}
      </div>
      <div className="focus-rail__foot">
        <b>{FOCUS_RAIL_FOOTER_KEYS}</b> {FOCUS_RAIL_FOOTER_CYCLE} <b>{FOCUS_RAIL_FOOTER_ENTER}</b> {FOCUS_RAIL_FOOTER_OPENS}
      </div>
    </aside>
  );
}
