/**
 * HOD Momo strip -- the compact alert strip across the top of the Scanner
 * board (approved UX redesign). One line per alert, newest on top; folds to
 * its header; drag the bottom edge to resize (whole rows, at most 40% of the
 * column). The component keeps the `HodMomoDock` name so the Scanner pages
 * and the sample shell import one thing.
 */
import { useCallback, useMemo, useRef, useState, type UIEvent } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
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
import { stripRowsToPx } from './hodMomoStripPersist';
import { fmtStripSince, stripAlertsForMode } from './hodMomoStripRows';
import { isAlertDockMode } from './scannerDockModes';
import { defaultHodMomentumVisibleStrategies } from './scannerPartition';
import { useHodMomoIntegrity } from './useHodMomoIntegrity';
import { useHodMomoStripResize } from './useHodMomoStripResize';
import { useStripNewAlerts } from './useStripNewAlerts';

const STRIP_OVERSCAN_ROWS = 6;

type Props = {
  /** Sample shell: open fixture trader instead of live Stock View. */
  onOpenTrading?: (symbol: string) => void;
  /** Row click. Defaults to the workspace's row selection (side panel follows). */
  onAlertSelect?: (symbol: string) => void;
};

export function HodMomoDock({ onOpenTrading, onAlertSelect }: Props) {
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
  } = useHodMomo();
  const { selectedSymbol, setSelectedSymbol, selectRowSymbol, openStockView } = useWorkspace();
  const sample = useSampleDataOptional();
  const rootRef = useRef<HTMLElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const [visibleStrategies, setVisibleStrategies] = useState<Set<number>>(
    defaultHodMomentumVisibleStrategies,
  );
  const integrity = useHodMomoIntegrity();
  const resize = useHodMomoStripResize({ rows, setRows, rootRef });

  const openTrading = onOpenTrading ?? openStockView;
  // Sample shell drives its own fixture Trader state -- it must not touch the
  // live traderViewActive via selectRowSymbol.
  const selectSymbol = onAlertSelect ?? (onOpenTrading ? setSelectedSymbol : selectRowSymbol);
  const mode: 'hod_momo' | 'running_up' = isAlertDockMode(dockMode) ? dockMode : 'hod_momo';

  const alerts = useMemo(
    () => stripAlertsForMode(stream.alerts, mode, mode === 'hod_momo' ? visibleStrategies : null),
    [stream.alerts, mode, visibleStrategies],
  );
  const newIds = useStripNewAlerts(stream.alerts);
  const since = useMemo(() => fmtStripSince(alerts), [alerts]);

  const strategyCounts = useMemo(() => {
    const c: Record<number, number> = {};
    for (const a of stream.alerts) c[a.strategy_id] = (c[a.strategy_id] ?? 0) + 1;
    return c;
  }, [stream.alerts]);
  const configColors = useMemo(() => {
    const out: Record<number, string> = {};
    for (const [sid, cfg] of Object.entries(config.state.strategies ?? {})) out[Number(sid)] = cfg.color;
    return out;
  }, [config.state.strategies]);

  const clearAlerts = useCallback(() => {
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
  }, [mode, sample]);

  const selectMode = (next: HodDockMode) => {
    setDockMode(next);
    if (collapsed) setCollapsed(false);
  };

  const toggleStrategy = (id: number) => {
    setVisibleStrategies((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onScroll = (e: UIEvent<HTMLDivElement>) => setScrollTop(e.currentTarget.scrollTop);
  const bodyPx = stripRowsToPx(rows);
  const range = computeVisibleRowRange(scrollTop, alerts.length, HOD_MOMO_STRIP_ROW_PX, bodyPx, STRIP_OVERSCAN_ROWS);
  const rendered = alerts.slice(range.startIndex, range.endIndex);

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
            onToggleStrategy={toggleStrategy}
            onClear={clearAlerts}
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
              <div className="hod-strip__empty" data-testid="hod-momo-strip-empty">
                {stream.connected ? HOD_MOMO_STRIP_EMPTY_WAITING : HOD_MOMO_STRIP_EMPTY_CONNECTING}
              </div>
            ) : (
              <>
                {range.topSpacerPx > 0 && <div style={{ height: range.topSpacerPx }} aria-hidden="true" />}
                {rendered.map((alert) => (
                  <HodMomoStripRow
                    key={alert.id}
                    alert={alert}
                    selected={selectedSymbol === alert.ticker}
                    isNew={newIds.has(alert.id)}
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
