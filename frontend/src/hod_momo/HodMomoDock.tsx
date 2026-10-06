/**
 * HOD Momo strip -- the compact alert strip across the top of the Scanner
 * board (approved UX redesign). One line per ticker per batch -- strategies
 * that fire together share a row with a count bubble -- newest on top; folds to
 * its header; drag the bottom edge to resize (whole rows, at most 40% of the
 * column). The component keeps the `HodMomoDock` name so the Scanner pages
 * and the sample shell import one thing.
 */
import { useCallback, useMemo, useRef, useState, type UIEvent } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { requestFocusList } from '../workspace';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { alertApp, confirmApp } from '../ux';
import { computeVisibleRowRange } from './HodMomoAlertTable';
import { HodMomoDebugPanel } from './HodMomoDebugPanel';
import { HodMomoSettings } from './HodMomoSettings';
import { HodMomoStripHeader } from './HodMomoStripHeader';
import { HodMomoStripMenu } from './HodMomoStripMenu';
import { HodMomoStripRow } from './HodMomoStripRow';
import { useHodMomo, type HodDockMode } from './HodMomoContext';
import {
  HOD_MOMO_STRIP_DEFAULT_ROWS,
  HOD_MOMO_STRIP_EMPTY_CONNECTING,
  HOD_MOMO_STRIP_EMPTY_WAITING,
  HOD_MOMO_STRIP_GRIP_LABEL,
  HOD_MOMO_STRIP_GRIP_TITLE,
  HOD_MOMO_STRIP_ROW_PX,
  hodMomoStripSinceLabel,
} from './hodMomoStripConstants';
import { groupIsNew, type StripAlertGroup } from './hodMomoStripGroups';
import { stripRowsToPx } from './hodMomoStripPersist';
import { fmtStripSince } from './hodMomoStripRows';
import { isAlertDockMode } from './scannerDockModes';
import { defaultHodMomentumVisibleStrategies } from './scannerPartition';
import { useHodMomoIntegrity } from './useHodMomoIntegrity';
import { useHodMomoStripResize } from './useHodMomoStripResize';
import { useHodStripView } from './useHodStripView';
import { hodReplayEmptyText, hodReplayFeed } from './hodMomoReplayCopy';
import type { AlertObject } from './types';

const STRIP_OVERSCAN_ROWS = 6;
const NO_ALERTS: AlertObject[] = [];
const NO_GROUPS: StripAlertGroup[] = [];
const NO_NEW_IDS: ReadonlySet<string> = new Set();
const NO_COLORS: Readonly<Record<number, string>> = {};
const DEFAULT_VISIBLE: ReadonlySet<number> = defaultHodMomentumVisibleStrategies();

type Props = {
  /** Sample shell / Desk: open the symbol their own way. `from` is the strip's
   * list (HOD Momo or Running Up), which the Trader's Focus rail follows. */
  onOpenTrading?: (symbol: string, from?: HodDockMode) => void;
  /** Row click. Defaults to the workspace's row selection (side panel follows). */
  onAlertSelect?: (symbol: string) => void;
};

export function HodMomoDock({ onOpenTrading, onAlertSelect }: Props) {
  const hod = useHodMomo();
  const {
    stream,
    config,
    dockMode,
    setDockMode,
    collapsed,
    setCollapsed,
    toggleCollapsed,
    rows,
    setRows,
    hodCount,
    runningUpCount,
    showHodSettings,
    setShowHodSettings,
    toggleHodSettings,
    replay = null,
    visibleStrategies = DEFAULT_VISIBLE,
    toggleStrategy,
  } = hod;
  const { selectedSymbol, setSelectedSymbol, selectRowSymbol, openStockView } = useWorkspace();
  const sample = useSampleDataOptional();
  const rootRef = useRef<HTMLElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const integrity = useHodMomoIntegrity();
  const resize = useHodMomoStripResize({ rows, setRows, rootRef });

  const mode: 'hod_momo' | 'running_up' = isAlertDockMode(dockMode) ? dockMode : 'hod_momo';
  const openTrading = useCallback((symbol: string) => {
    if (onOpenTrading) onOpenTrading(symbol, mode);
    else openStockView(symbol, { from: mode });
  }, [onOpenTrading, openStockView, mode]);
  // Sample shell drives its own fixture Trader state -- it must not touch the
  // live traderViewActive via selectRowSymbol.
  const select = onAlertSelect ?? (onOpenTrading ? setSelectedSymbol : selectRowSymbol);
  // A strip pick takes the Trader's Focus rail to this list, as an open does.
  const selectSymbol = useCallback((symbol: string) => {
    requestFocusList(mode);
    select(symbol);
  }, [select, mode]);

  // The same rows the Trader's Focus rail half draws (useHodStripView).
  const view = useHodStripView(hod, mode);
  const alerts = view?.alerts ?? NO_ALERTS;
  const groups = view?.groups ?? NO_GROUPS;
  const newIds = view?.newIds ?? NO_NEW_IDS;
  const configColors = view?.strategyColors ?? NO_COLORS;
  const since = useMemo(() => fmtStripSince(alerts), [alerts]);

  const strategyCounts = useMemo(() => {
    const c: Record<number, number> = {};
    for (const a of stream.alerts) c[a.strategy_id] = (c[a.strategy_id] ?? 0) + 1;
    return c;
  }, [stream.alerts]);

  const clearAlerts = useCallback(() => {
    if (replay) return;
    const label = mode === 'running_up' ? 'Running Up' : 'HOD Momentum';
    if (sample) {
      void alertApp({
        title: 'Sample data',
        message: `${label} alerts are fixtures; nothing is cleared on the server.`,
      });
      return;
    }
    void confirmApp({
      title: `Clear today's ${label} alerts?`,
      message:
        'This clears the shared HOD Momentum + Running Up alert store for today. '
        + 'Past days in History are kept. New alerts will keep arriving.',
      confirmLabel: 'Clear',
      tone: 'warning',
    }).then((ok) => {
      if (!ok) return;
      novaFetch(`${API_BASE_URL}/api/hod-momo/alerts`, { method: 'DELETE' }).catch((err) => {
        console.error('Clear HOD/Running Up alerts failed', err);
      });
    });
  }, [mode, sample, replay]);

  const selectMode = (next: HodDockMode) => {
    setDockMode(next);
    if (collapsed) setCollapsed(false);
  };

  const onToggleStrategy = (id: number) => toggleStrategy?.(id);

  const onScroll = (e: UIEvent<HTMLDivElement>) => setScrollTop(e.currentTarget.scrollTop);
  const bodyPx = stripRowsToPx(rows);
  const range = computeVisibleRowRange(scrollTop, groups.length, HOD_MOMO_STRIP_ROW_PX, bodyPx, STRIP_OVERSCAN_ROWS);
  const rendered = groups.slice(range.startIndex, range.endIndex);

  return (
    <section
      ref={rootRef}
      className={`hod-strip${collapsed ? ' is-folded' : ''}${resize.dragging ? ' is-dragging' : ''}`}
      data-testid="hod-momo-dock"
      data-dock-mode={mode}
      data-collapsed={collapsed ? '1' : '0'}
      aria-label="HOD Momo strip"
    >
      <HodMomoStripHeader
        sinceLabel={hodMomoStripSinceLabel(alerts.length, since)}
        integrity={integrity}
        connected={stream.connected}
        feedLabel={replay ? hodReplayFeed(replay) : null}
        dockMode={mode}
        onSelectMode={selectMode}
        hodCount={hodCount}
        runningUpCount={runningUpCount}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
        menuOpen={menuOpen}
        onToggleMenu={() => setMenuOpen((v) => !v)}
        menu={(
          <HodMomoStripMenu
            showStrategies={mode === 'hod_momo'}
            visibleStrategies={visibleStrategies}
            strategyCounts={strategyCounts}
            configColors={configColors}
            debugOpen={debugOpen}
            onToggleStrategy={onToggleStrategy}
            onClear={clearAlerts}
            clearDisabled={replay != null}
            onConfigure={toggleHodSettings}
            onToggleDebug={() => {
              setDebugOpen((v) => !v);
              if (collapsed) setCollapsed(false);
            }}
            onClose={() => setMenuOpen(false)}
          />
        )}
      />

      {!collapsed && (
        <>
          <div
            className="hod-strip__body"
            style={{ height: bodyPx }}
            data-testid="hod-momo-dock-body"
            data-rows={rows}
            data-total-count={alerts.length}
            data-row-count={groups.length}
            role="table"
            onScroll={onScroll}
          >
            {debugOpen ? (
              <HodMomoDebugPanel
                selectedSymbol={selectedSymbol}
                onSelectSymbol={selectSymbol}
                onOpenTrading={openTrading}
              />
            ) : alerts.length === 0 ? (
              <div
                className={`hod-strip__empty${stream.feedError ? ' hod-strip__empty--error' : ''}`}
                data-testid="hod-momo-strip-empty"
                data-replay={replay ? '1' : undefined}
                role={stream.feedError ? 'alert' : undefined}
              >
                {replay
                  ? hodReplayEmptyText(replay)
                  : stream.feedError
                    ?? (stream.connected ? HOD_MOMO_STRIP_EMPTY_WAITING : HOD_MOMO_STRIP_EMPTY_CONNECTING)}
              </div>
            ) : (
              <>
                {range.topSpacerPx > 0 && <div style={{ height: range.topSpacerPx }} aria-hidden="true" />}
                {rendered.map((group) => (
                  <HodMomoStripRow
                    key={group.key}
                    group={group}
                    selected={selectedSymbol === group.ticker}
                    isNew={groupIsNew(group, newIds)}
                    strategyColors={configColors}
                    onSelect={selectSymbol}
                    onOpenTrading={openTrading}
                  />
                ))}
                {range.bottomSpacerPx > 0 && <div style={{ height: range.bottomSpacerPx }} aria-hidden="true" />}
              </>
            )}
          </div>
          <div
            className="hod-strip__grip"
            role="separator"
            aria-orientation="horizontal"
            aria-label={HOD_MOMO_STRIP_GRIP_LABEL}
            title={HOD_MOMO_STRIP_GRIP_TITLE}
            data-testid="hod-momo-strip-grip"
            onPointerDown={resize.onPointerDown}
            onDoubleClick={() => setRows(HOD_MOMO_STRIP_DEFAULT_ROWS)}
          />
        </>
      )}

      {showHodSettings && (
        <div className="hod-strip__settings">
          <HodMomoSettings config={config} onClose={() => setShowHodSettings(false)} />
        </div>
      )}
    </section>
  );
}
