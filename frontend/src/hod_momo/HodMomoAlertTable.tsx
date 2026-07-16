import { useEffect, useRef, useState, type UIEvent } from 'react';
import {
  HOD_MOMO_COLUMNS,
  HOD_MOMO_EMPTY_CONNECTING,
  HOD_MOMO_EMPTY_WAITING,
  HOD_MOMO_HEADER_HEIGHT_PX,
  HOD_MOMO_LOAD_MORE_THRESHOLD_PX,
  HOD_MOMO_RENDER_BATCH_SIZE,
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_VISIBLE_ROWS,
  STRATEGY_META,
} from '../constants';
import type { AlertObject } from './types';
import { HodMomoAlertRow } from './HodMomoAlertRow';

function StrategyFilterDropdown({
  enabledStrategies,
  counts,
  onToggle,
  onClose,
  configColors,
}: {
  enabledStrategies: Set<number>;
  counts: Record<number, number>;
  onToggle: (id: number) => void;
  onClose: () => void;
  configColors: Record<number, string>;
}) {
  return (
    <div className="hod-filter-dropdown">
      <div className="hod-filter-header">
        <span>Filter Strategies</span>
        <button className="hod-filter-close" onClick={onClose}>✕</button>
      </div>
      <label className="hod-filter-row hod-filter-all">
        <input
          type="checkbox"
          checked={enabledStrategies.size === STRATEGY_META.length}
          onChange={() => {
            if (enabledStrategies.size === STRATEGY_META.length) {
              STRATEGY_META.forEach(s => enabledStrategies.has(s.id) && onToggle(s.id));
            } else {
              STRATEGY_META.forEach(s => !enabledStrategies.has(s.id) && onToggle(s.id));
            }
          }}
        />
        <span>Select / Unselect All</span>
      </label>
      {STRATEGY_META.map(s => {
        const color = configColors[s.id] || s.color;
        return (
          <label key={s.id} className="hod-filter-row">
            <input
              type="checkbox"
              checked={enabledStrategies.has(s.id)}
              onChange={() => onToggle(s.id)}
            />
            <span className="hod-filter-dot" style={{ background: color }} />
            <span className="hod-filter-name">{s.name}</span>
            {(counts[s.id] ?? 0) > 0 && (
              <span className="hod-filter-count">{counts[s.id]}</span>
            )}
          </label>
        );
      })}
    </div>
  );
}

export interface HodMomoAlertTableProps {
  alerts: AlertObject[];
  connected: boolean;
  consolidationSec: number;
  configColors: Record<number, string>;
  strategyCounts: Record<number, number>;
  visibleStrategies: Set<number>;
  onToggleStrategy: (id: number) => void;
  selectedSymbol: string | null;
  onSelectSymbol: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
}

export function nextHodMomoRenderedCount(current: number, total: number): number {
  return Math.min(current + HOD_MOMO_RENDER_BATCH_SIZE, total);
}

/** Bounded HOD table with incremental row mounting and scroll-freeze. */
export function HodMomoAlertTable({
  alerts,
  connected,
  consolidationSec,
  configColors,
  strategyCounts,
  visibleStrategies,
  onToggleStrategy,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: HodMomoAlertTableProps) {
  const [showFilterDropdown, setShowFilterDropdown] = useState(false);
  const [renderedCount, setRenderedCount] = useState(HOD_MOMO_RENDER_BATCH_SIZE);
  // Freeze: when user has scrolled down, hold a snapshot so new alerts don't
  // shift content under their finger. Show a "▲ N new" pill instead.
  const [isScrolledDown, setIsScrolledDown] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomTriggeredRef = useRef(false);
  // Snapshot captured at the moment the user scrolls away from the top.
  const frozenSnapshotRef = useRef<{ list: AlertObject[]; total: number } | null>(null);
  // Track previous scrolled-down state for edge-detection in the scroll handler.
  const prevScrolledRef = useRef(false);
  // Always-current refs so the scroll handler can read the latest render values.
  const renderedCountRef = useRef(renderedCount);
  const alertsRef = useRef(alerts);
  renderedCountRef.current = renderedCount;
  alertsRef.current = alerts;

  const viewportHeight = HOD_MOMO_VISIBLE_ROWS * HOD_MOMO_ROW_HEIGHT_PX;
  const empty = alerts.length === 0;

  // Derived display list: frozen snapshot when scrolled, live slice otherwise.
  const liveDisplayAlerts = alerts.slice(0, renderedCount);
  const displayAlerts = frozenSnapshotRef.current?.list ?? liveDisplayAlerts;
  const newArrived = frozenSnapshotRef.current
    ? Math.max(0, alerts.length - frozenSnapshotRef.current.total)
    : 0;

  // Reset rendered count and unfreeze when strategy filter changes.
  useEffect(() => {
    frozenSnapshotRef.current = null;
    prevScrolledRef.current = false;
    setIsScrolledDown(false);
    setRenderedCount(HOD_MOMO_RENDER_BATCH_SIZE);
    bottomTriggeredRef.current = false;
    scrollRef.current?.scrollTo({ top: 0 });
  }, [visibleStrategies]);

  // Reset when alert list becomes empty (cleared).
  useEffect(() => {
    if (empty) {
      frozenSnapshotRef.current = null;
      prevScrolledRef.current = false;
      setIsScrolledDown(false);
      setRenderedCount(HOD_MOMO_RENDER_BATCH_SIZE);
      bottomTriggeredRef.current = false;
    }
  }, [empty]);

  function jumpToTop() {
    frozenSnapshotRef.current = null;
    prevScrolledRef.current = false;
    setIsScrolledDown(false);
    setRenderedCount(HOD_MOMO_RENDER_BATCH_SIZE);
    bottomTriggeredRef.current = false;
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const el = event.currentTarget;
    const scrolledDown = el.scrollTop > 0;

    // Edge detection: transition into or out of scrolled state.
    if (scrolledDown !== prevScrolledRef.current) {
      prevScrolledRef.current = scrolledDown;
      if (scrolledDown) {
        // Freeze the current display so new alerts won't shift content.
        frozenSnapshotRef.current = {
          list: alertsRef.current.slice(0, renderedCountRef.current),
          total: alertsRef.current.length,
        };
      } else {
        // Scrolled back to top — unfreeze and show the live list.
        frozenSnapshotRef.current = null;
      }
      setIsScrolledDown(scrolledDown);
      return; // Skip bottom-trigger logic on a freeze/unfreeze transition.
    }

    // Bottom-load logic — only when not frozen.
    if (frozenSnapshotRef.current) return;

    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom > HOD_MOMO_LOAD_MORE_THRESHOLD_PX) {
      bottomTriggeredRef.current = false;
      return;
    }
    if (!bottomTriggeredRef.current && renderedCountRef.current < alertsRef.current.length) {
      bottomTriggeredRef.current = true;
      setRenderedCount(current => nextHodMomoRenderedCount(current, alertsRef.current.length));
    }
  }

  return (
    <div className="hod-table-container">
      {isScrolledDown && newArrived > 0 && (
        <button
          type="button"
          className="hod-new-pill"
          onClick={jumpToTop}
          aria-label={`${newArrived} new alert${newArrived === 1 ? '' : 's'} — click to jump to top`}
        >
          ▲ {newArrived} new alert{newArrived === 1 ? '' : 's'}
        </button>
      )}
      <div
        className="table-wrapper hod-table-wrapper"
        ref={scrollRef}
        onScroll={handleScroll}
        data-rendered-count={displayAlerts.length}
        style={{
          height: viewportHeight + HOD_MOMO_HEADER_HEIGHT_PX,
          maxHeight: viewportHeight + HOD_MOMO_HEADER_HEIGHT_PX,
        }}
      >
        <table>
          <thead>
            <tr>
              {HOD_MOMO_COLUMNS.map(([key, label]) => (
                <th
                  key={key}
                  className={`sortable-th${key === 'strategy' ? ' hod-strategy-th' : ''}`}
                  onClick={key === 'strategy' ? () => setShowFilterDropdown(x => !x) : undefined}
                  style={key === 'strategy' ? { cursor: 'pointer', userSelect: 'none' } : undefined}
                >
                  <span className="th-inner">
                    {label}
                    {key === 'strategy' && (
                      <span className="hod-filter-icon">▾</span>
                    )}
                  </span>
                  {key === 'strategy' && showFilterDropdown && (
                    <StrategyFilterDropdown
                      enabledStrategies={visibleStrategies}
                      counts={strategyCounts}
                      onToggle={onToggleStrategy}
                      onClose={() => setShowFilterDropdown(false)}
                      configColors={configColors}
                    />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {empty ? (
              <tr>
                <td colSpan={HOD_MOMO_COLUMNS.length} className="hod-empty-cell">
                  {connected ? HOD_MOMO_EMPTY_WAITING : HOD_MOMO_EMPTY_CONNECTING}
                </td>
              </tr>
            ) : (
              <>
                {displayAlerts.map(alert => (
                  <HodMomoAlertRow
                    key={alert.id}
                    alert={alert}
                    strategyColorOverride={configColors[alert.strategy_id]}
                    selected={selectedSymbol === alert.ticker}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    consolidationSec={consolidationSec}
                  />
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
