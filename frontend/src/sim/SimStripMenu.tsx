/**
 * The strip's `⋯` menu: what the Sim desk is showing, Follow wall clock, Load
 * recording (the Day / Ticker pickers, as a small popover instead of strip
 * chrome), Close replay, and the Historical replay panel. The NO REPLAY /
 * LIVE EDGE / CAPTURE / HISTORICAL line lives here, never as a banner.
 */
import { useState } from 'react';
import { Popover } from 'radix-ui';
import { MoreHorizontal } from 'lucide-react';
import {
  SIM_STRIP_MENU_ARIA,
  SIM_STRIP_MENU_CLOSE_REPLAY,
  SIM_STRIP_MENU_DAY,
  SIM_STRIP_MENU_FOLLOW,
  SIM_STRIP_MENU_LOAD_RECORDING,
  SIM_STRIP_MENU_NO_RECORDING,
  SIM_STRIP_MENU_PICK_TICKER,
  SIM_STRIP_MENU_TICKER,
} from '../constantGroups/trader_chrome';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';
import { missingLabel } from './simCoverage';
import {
  SIM_LIVE_EDGE_EMPTY_NOTE, SIM_LIVE_EDGE_SOURCE, SIM_TAB_NO_REPLAY_TITLE, SIM_TAB_WHAT_SIM_IS, simCaptureMissingLabel,
} from './simConstants';
import type { SimClockState } from './simClockTypes';
import type { CaptureSessions } from './useSimSessionController';

interface Props {
  clock: SimClockState | null;
  sessions: CaptureSessions | undefined;
  day: string;
  symbol: string;
  busy: Set<string>;
  liveEdge: boolean;
  atWallClock: boolean;
  setDay: (day: string) => void;
  setSymbol: (symbol: string) => void;
  applyReplay: (day: string, symbol: string) => Promise<void>;
  onFollowWall: () => Promise<void>;
}

export function SimStripMenu({
  clock, sessions, day, symbol, busy, liveEdge, atWallClock, setDay, setSymbol, applyReplay, onFollowWall,
}: Props) {
  const [open, setOpen] = useState(false);
  const historical = clock?.replay_source === 'historical';
  const capture = clock?.replay_source === 'capture';
  const source = liveEdge ? SIM_LIVE_EDGE_SOURCE : historical ? 'HISTORICAL' : capture ? 'CAPTURE' : 'NO REPLAY';
  const tickers = sessions?.tickers_by_day?.[day] ?? [];
  const diagnostics = capture ? clock?.replay_load : null;
  const invalid = diagnostics
    ? (diagnostics.malformed_rows ?? 0) + (diagnostics.invalid_timestamp_rows ?? 0) + (diagnostics.invalid_rows ?? 0)
    : 0;
  const nothingLoaded = !historical && !capture && clock?.replay_ok !== false;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button type="button" className="sim-strip__more" aria-label={SIM_STRIP_MENU_ARIA} title={SIM_STRIP_MENU_ARIA}
          data-testid="sim-strip-menu">
          <MoreHorizontal size={16} aria-hidden="true" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content side="bottom" align="end" sideOffset={6} collisionPadding={12} className="sim-strip__menu"
          aria-label={SIM_STRIP_MENU_ARIA}>
          <div className="sim-strip__menu-state">
            <span className="sim-strip__menu-source" data-testid="sim-replay-source">{source}</span>
            {nothingLoaded && (
              <span className="sim-muted" data-testid="sim-replay-empty">
                {liveEdge ? SIM_LIVE_EDGE_EMPTY_NOTE : `${SIM_TAB_NO_REPLAY_TITLE}. ${SIM_TAB_WHAT_SIM_IS}`}
              </span>
            )}
            {diagnostics && (
              <span role="status" className="sim-capture-diagnostics">
                L2: {(diagnostics.l2_loaded ?? 0).toLocaleString()} / {(diagnostics.l2_total ?? 0).toLocaleString()} snapshots
                {diagnostics.l2_decimated && '  -  sampled depth (decimated)'}
                {invalid > 0 && `  -  ${invalid.toLocaleString()} invalid rows discarded`}
                {diagnostics.legacy_schema && '  -  legacy format migrated'}
              </span>
            )}
          </div>
          <button type="button" className="sim-strip__menu-item" disabled={atWallClock || busy.has('follow')}
            data-testid="sim-strip-follow-wall"
            onClick={() => { void onFollowWall(); }}>
            {SIM_STRIP_MENU_FOLLOW}{atWallClock ? <em>on</em> : null}
          </button>
          <div className="sim-strip__menu-group" data-testid="sim-strip-load-recording">
            <span className="sim-strip__menu-title">{SIM_STRIP_MENU_LOAD_RECORDING}</span>
            {historical ? (
              <button type="button" className="sim-strip__menu-item" disabled={busy.has('replay')}
                onClick={() => { setDay(''); setSymbol(''); void applyReplay('', ''); }}>
                {SIM_STRIP_MENU_CLOSE_REPLAY}
              </button>
            ) : (
              <>
                <label className="sim-strip__picker" title="Captured session date">{SIM_STRIP_MENU_DAY}
                  <select data-testid="sim-replay-day" value={day} disabled={busy.has('replay')} onChange={event => {
                    const next = event.target.value; setDay(next); setSymbol(''); if (!next) void applyReplay('', '');
                  }}>
                    <option value="">{SIM_STRIP_MENU_NO_RECORDING}</option>
                    {(sessions?.days ?? []).map(item => <option key={item.date} value={item.date}>{item.date} ({item.ticker_count})</option>)}
                  </select>
                </label>
                <label className="sim-strip__picker" title="Captured ticker">{SIM_STRIP_MENU_TICKER}
                  <select data-testid="sim-replay-ticker" value={symbol} disabled={!day || busy.has('replay')} onChange={event => {
                    const next = event.target.value; setSymbol(next); void applyReplay(day, next);
                  }}>
                    <option value="">{day ? SIM_STRIP_MENU_PICK_TICKER : '--'}</option>
                    {tickers.map(ticker => (
                      <option key={ticker.symbol} value={ticker.symbol} disabled={ticker.usable === false || ticker.empty}>
                        {ticker.symbol} · {ticker.usable === false || ticker.empty
                          ? ticker.unavailable_reason ?? 'Empty recording'
                          : ticker.prints < 0 ? 'data present' : `${ticker.prints}p`}
                        {ticker.missing_sec ? ` · ${simCaptureMissingLabel(missingLabel(ticker.missing_sec))}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>
          <div className="sim-strip__menu-group sim-session-header">
            <HistoricalReplayPanel />
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
