/**
 * AppShell top dock — collapsed strip or expanded HOD / Running Up table.
 */
import { useCallback, useRef } from 'react';
import { ResizeHandle } from '../components/ResizeHandle';
import { HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX, API_BASE_URL } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { novaFetch } from '../api/novaFetch';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { alertApp, confirmApp } from '../ux';
import { useHodMomo, type HodDockMode } from './HodMomoContext';
import { HodMomoSection } from './HodMomoSection';

function formatCount(n: number): string {
  if (n <= 0) return '';
  if (n > 99) return '99+';
  return String(n);
}

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
    openStockView,
  } = useWorkspace();
  const sample = useSampleDataOptional();
  const dragStart = useRef<{ y: number; h: number } | null>(null);
  const openTrading = onOpenTrading ?? openStockView;

  const clearAlerts = useCallback(() => {
    const label = dockMode === 'hod_momo' ? 'HOD Momentum' : 'Running Up';
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
  };

  return (
    <section
      className={`hod-momo-dock${collapsed ? ' hod-momo-dock--collapsed' : ''}`}
      data-testid="hod-momo-dock"
      data-dock-mode={dockMode}
      data-collapsed={collapsed ? '1' : '0'}
      aria-label="HOD Momo scanner dock"
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
          title={collapsed ? 'Expand HOD dock' : 'Collapse HOD dock'}
        >
          <span className="hod-momo-dock__chevron" aria-hidden="true">
            {collapsed ? '▸' : '▾'}
          </span>
        </button>

        <div
          className="hod-momo-dock__modes"
          role="tablist"
          aria-label="HOD scanner mode"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            role="tab"
            aria-selected={dockMode === 'hod_momo'}
            className={
              dockMode === 'hod_momo'
                ? 'hod-momo-dock__mode is-active'
                : 'hod-momo-dock__mode'
            }
            data-testid="hod-momo-dock-mode-hod"
            onClick={() => selectMode('hod_momo')}
          >
            HOD Momo
            {hodCount > 0 ? (
              <span className="hod-momo-dock__count">{formatCount(hodCount)}</span>
            ) : null}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={dockMode === 'running_up'}
            className={
              dockMode === 'running_up'
                ? 'hod-momo-dock__mode is-active'
                : 'hod-momo-dock__mode'
            }
            data-testid="hod-momo-dock-mode-ru"
            onClick={() => selectMode('running_up')}
          >
            Running Up
            {runningUpCount > 0 ? (
              <span className="hod-momo-dock__count">
                {formatCount(runningUpCount)}
              </span>
            ) : null}
          </button>
        </div>

        <span
          className={`hod-momo-dock__live${stream.connected ? ' is-live' : ''}`}
          title={stream.connected ? 'HOD feed connected' : 'HOD feed disconnected'}
        >
          {stream.connected ? 'Live' : 'Offline'}
        </span>

        <div className="hod-momo-dock__actions" onClick={(e) => e.stopPropagation()}>
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
      </header>

      {!collapsed && (
        <>
          <div
            className="hod-momo-dock__body"
            style={{ height: heightPx }}
            data-testid="hod-momo-dock-body"
          >
            <HodMomoSection
              activeTab={dockMode}
              hodMomoStream={stream}
              hodMomoConfig={config}
              selectedSymbol={selectedSymbol}
              onSelect={setSelectedSymbol}
              onOpenTrading={openTrading}
              showHodSettings={showHodSettings}
              onToggleHodSettings={toggleHodSettings}
              onCloseHodSettings={() => setShowHodSettings(false)}
            />
          </div>
          <ResizeHandle
            orientation="horizontal"
            label="Resize HOD Momo dock"
            onPointerDown={onResizePointerDown}
            onDoubleClick={() => setHeightPx(HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX)}
          />
        </>
      )}
    </section>
  );
}
