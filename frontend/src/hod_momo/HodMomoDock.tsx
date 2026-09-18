/**
 * AppShell top dock — collapsed strip or expanded HOD / roster scanner table.
 */
import { useCallback, useEffect, useRef } from 'react';
import { ResizeHandle } from '../components/ResizeHandle';
import { HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX, API_BASE_URL } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { novaFetch } from '../api/novaFetch';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useScannerDockRows } from '../scanner/useScannerDockRows';
import { alertApp, confirmApp } from '../ux';
import { HodMomoDockModes } from './HodMomoDockModes';
import { HodMomoDockRoster } from './HodMomoDockRoster';
import { useHodMomo, type HodDockMode } from './HodMomoContext';
import { HodMomoSection } from './HodMomoSection';
import { HodMomoSoundToggle } from './HodMomoSoundToggle';
import { isAlertDockMode, isRosterDockMode } from './scannerDockModes';

type Props = {
  /** Sample shell: open fixture trader instead of live Stock View. */
  onOpenTrading?: (symbol: string) => void;
};

export function HodMomoDock({ onOpenTrading }: Props) {
  const {
    stream,
    config,
    dockMode,
    setDockMode,
    collapsed,
    setCollapsed,
    toggleCollapsed,
    heightPx,
    setHeightPx,
    hodCount,
    runningUpCount,
    showHodSettings,
    setShowHodSettings,
    toggleHodSettings,
  } = useHodMomo();
  const {
    selectedSymbol,
    setSelectedSymbol,
    selectRowSymbol,
    openStockView,
  } = useWorkspace();
  const sample = useSampleDataOptional();
  const roster = useScannerDockRows();
  const dragStart = useRef<{ y: number; h: number } | null>(null);
  const openTrading = onOpenTrading ?? openStockView;
  // Sample shell drives its own fixture Trader state (see SampleShell) --
  // it must not read/mutate the live traderViewActive via selectRowSymbol.
  const selectSymbol = onOpenTrading ? setSelectedSymbol : selectRowSymbol;
  const alertMode = isAlertDockMode(dockMode);

  // Declare the dock's table for L1 streaming whenever it changes, including on
  // mount: dockMode is restored from the previous session while the main tab
  // resets to Gappers, so a click-only hint left a visible dock roster (e.g.
  // Gainers) with no price_patch at all after every reload.
  const setL1DockTab = roster?.setL1DockTab ?? null;
  useEffect(() => {
    if (!setL1DockTab) return;
    setL1DockTab(isRosterDockMode(dockMode) ? dockMode : null);
  }, [dockMode, setL1DockTab]);

  const clearAlerts = useCallback(() => {
    const label = dockMode === 'running_up' ? 'Running Up' : 'HOD Momentum';
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
      novaFetch(`${API_BASE_URL}/api/hod-momo/alerts`, { method: 'DELETE' }).catch(
        (err) => {
          console.error('Clear HOD/Running Up alerts failed', err);
        },
      );
    });
  }, [dockMode, sample]);

  const onResizePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      const target = e.currentTarget as HTMLElement;
      target.setPointerCapture(e.pointerId);
      dragStart.current = { y: e.clientY, h: heightPx };

      const onMove = (ev: PointerEvent) => {
        if (!dragStart.current) return;
        setHeightPx(dragStart.current.h + (ev.clientY - dragStart.current.y));
      };
      const onUp = (ev: PointerEvent) => {
        target.releasePointerCapture(ev.pointerId);
        dragStart.current = null;
        target.removeEventListener('pointermove', onMove);
        target.removeEventListener('pointerup', onUp);
        target.removeEventListener('pointercancel', onUp);
      };
      target.addEventListener('pointermove', onMove);
      target.addEventListener('pointerup', onUp);
      target.addEventListener('pointercancel', onUp);
    },
    [heightPx, setHeightPx],
  );

  const selectMode = (mode: HodDockMode) => {
    setDockMode(mode);
    if (collapsed) setCollapsed(false);
  };

  const bodyIsRoster = isRosterDockMode(dockMode) && roster != null;

  return (
    <section
      className={`hod-momo-dock${collapsed ? ' hod-momo-dock--collapsed' : ''}`}
      data-testid="hod-momo-dock"
      data-dock-mode={dockMode}
      data-collapsed={collapsed ? '1' : '0'}
      aria-label="Scanner dock"
    >
      <header
        className="hod-momo-dock__bar"
        onClick={(e) => {
          const el = e.target as HTMLElement;
          if (el.closest('button')) return;
          toggleCollapsed();
        }}
      >
        <button
          type="button"
          className="hod-momo-dock__toggle"
          onClick={(e) => {
            e.stopPropagation();
            toggleCollapsed();
          }}
          aria-expanded={!collapsed}
          data-testid="hod-momo-dock-toggle"
          title={collapsed ? 'Expand scanner dock' : 'Collapse scanner dock'}
        >
          <span className="hod-momo-dock__chevron" aria-hidden="true">
            {collapsed ? '▸' : '▾'}
          </span>
        </button>

        <HodMomoDockModes
          dockMode={dockMode}
          onSelect={selectMode}
          hodCount={hodCount}
          runningUpCount={runningUpCount}
          rosterCounts={roster?.counts ?? null}
        />

        <span
          className={`hod-momo-dock__live${stream.connected ? ' is-live' : ''}`}
          title={stream.connected ? 'HOD feed connected' : 'HOD feed disconnected'}
        >
          {stream.connected ? 'Live' : 'Offline'}
        </span>

        {alertMode ? (
          <div className="hod-momo-dock__actions" onClick={(e) => e.stopPropagation()}>
            {dockMode === 'hod_momo' ? (
              <HodMomoSoundToggle className="hod-momo-dock__action hod-momo-dock__sound" />
            ) : null}
            <button
              type="button"
              className="hod-momo-dock__action"
              onClick={clearAlerts}
              title="Clear today's shared HOD / Running Up alerts"
              data-testid="hod-momo-dock-clear"
            >
              Clear
            </button>
            <button
              type="button"
              className="hod-momo-dock__action"
              onClick={toggleHodSettings}
              title="Configure HOD Momentum strategies"
              data-testid="hod-momo-dock-configure"
            >
              Configure
            </button>
          </div>
        ) : (
          <div className="hod-momo-dock__actions" />
        )}
      </header>

      {!collapsed && (
        <>
          <div
            className="hod-momo-dock__body"
            style={{ height: heightPx }}
            data-testid="hod-momo-dock-body"
          >
            {bodyIsRoster ? (
              <HodMomoDockRoster
                mode={dockMode}
                rows={roster}
                selectedSymbol={selectedSymbol}
                onSelect={selectSymbol}
                onOpenTrading={openTrading}
              />
            ) : (
              <HodMomoSection
                activeTab={alertMode ? dockMode : 'hod_momo'}
                hodMomoStream={stream}
                hodMomoConfig={config}
                selectedSymbol={selectedSymbol}
                onSelect={selectSymbol}
                onOpenTrading={openTrading}
                showHodSettings={showHodSettings}
                onToggleHodSettings={toggleHodSettings}
                onCloseHodSettings={() => setShowHodSettings(false)}
              />
            )}
          </div>
          <ResizeHandle
            orientation="horizontal"
            label="Resize scanner dock"
            onPointerDown={onResizePointerDown}
            onDoubleClick={() => setHeightPx(HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX)}
          />
        </>
      )}
    </section>
  );
}
