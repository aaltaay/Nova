/**
 * Focus list rail (approved redesign rev. 2 / 7): a collapsible ~220 px strip
 * between the navigation rail and the charts that mirrors any scanner list.
 * Header `FOCUS · <list> N ▾` (the caret picks a scanner tab module from the
 * registry), `Open Scanner`, collapse chevron. Rows: REC dot, bot dot (filled
 * = allowlisted and this desk holds the depth line -- a live Trader tab or a
 * recording; hollow = allowlisted, quiet), symbol, price, signed gap, catalyst
 * chip or `no news`. ↑ ↓ cycle, Enter opens. Data is the live scanner feed
 * the workspace already holds; without one the rail says so.
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
  FOCUS_RAIL_OPEN_SCANNER,
  FOCUS_RAIL_PICK_ARIA,
  FOCUS_RAIL_REC_TITLE,
  FOCUS_RAIL_TITLE,
  TRADER_CATALYST_NONE,
  focusRailEmpty,
  focusRailNotMirrored,
} from '../constantGroups/trader_chrome';
import { useLiveScannerFeedOptional } from '../scanner/ScannerDataContext';
import { useSettingsOptional } from '../settings/SettingsContext';
import { listTabModules } from '../workspace/registry';
import { writePersistedScannerTab } from '../workspace/scannerActiveTabPersist';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  focusRowsFor, readFocusRailState, stepCursor, writeFocusRailState, type FocusRailState,
} from './focusRailState';
import { formatSignedPct, pctTone } from './tabContext';
import './focusRail.css';

export function FocusRail() {
  const feed = useLiveScannerFeedOptional();
  const settings = useSettingsOptional();
  const { activeTraderSymbol, traderLiveTabs, openStockView, showScannerView } = useWorkspace();
  const { isAllowed } = useBotAllowlist();
  useSyncExternalStore(subscribeSessionRecord, () => getRecordingSymbols().join(','), () => '');
  const [state, setState] = useState<FocusRailState>(readFocusRailState);
  const [cursor, setCursor] = useState(-1);
  const modules = useMemo(() => listTabModules(), []);
  const module = modules.find(m => m.id === state.list) ?? modules[0];
  const filterRows = settings?.exchangeFilter?.filterRows;
  const rows = useMemo(
    () => focusRowsFor(state.list, feed, filterRows),
    [state.list, feed, filterRows],
  );

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
        <button type="button" className="focus-rail__link" data-testid="focus-rail-open-scanner"
          onClick={() => { writePersistedScannerTab(state.list as Parameters<typeof writePersistedScannerTab>[0]); showScannerView(); }}>
          {FOCUS_RAIL_OPEN_SCANNER}
        </button>
        <button type="button" className="focus-rail__collapse" aria-label={FOCUS_RAIL_COLLAPSE} title={FOCUS_RAIL_COLLAPSE}
          data-testid="focus-rail-collapse" onClick={() => update({ collapsed: true })}>
          <ChevronLeft size={14} aria-hidden="true" />
        </button>
      </div>
      <div className="focus-rail__rows" role="listbox" aria-label={module?.title ?? state.list} data-testid="focus-rail-rows">
        {!feed ? (
          <p className="focus-rail__absent" data-testid="focus-rail-absent">{FOCUS_RAIL_NO_FEED}</p>
        ) : rows == null ? (
          <p className="focus-rail__absent" data-testid="focus-rail-absent">{focusRailNotMirrored(module?.title ?? state.list)}</p>
        ) : rows.length === 0 ? (
          <p className="focus-rail__absent" data-testid="focus-rail-absent">{focusRailEmpty(module?.title ?? state.list)}</p>
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
              <span className="focus-rail__px">{row.price != null ? row.price.toFixed(2) : '—'}</span>
              <span className={`focus-rail__gap focus-rail__gap--${pctTone(row.gapPct)}`}>{formatSignedPct(row.gapPct)}</span>
              {row.catalyst ? (
                <span className="focus-rail__chip" title={row.headline ? `${row.catalyst} · ${row.headline}` : row.catalyst}>{row.catalyst}</span>
              ) : (
                <span className="focus-rail__chip focus-rail__chip--none">{TRADER_CATALYST_NONE}</span>
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
