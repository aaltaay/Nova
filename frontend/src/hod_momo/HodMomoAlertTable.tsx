import { useCallback, useEffect, useRef, useState, type UIEvent } from 'react';
import {
  HOD_MOMO_COLUMNS,
  HOD_MOMO_EMPTY_CONNECTING,
  HOD_MOMO_EMPTY_WAITING,
  HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
  HOD_MOMO_HEADER_HEIGHT_PX,
  HOD_MOMO_OVERSCAN_ROWS,
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_VISIBLE_ROWS,
  STRATEGY_META,
  type StrategyMeta,
} from '../constants';
import type { AlertObject } from './types';
import { HodMomoAlertRow } from './HodMomoAlertRow';

export interface VisibleRowRange {
  startIndex: number;
  /** Exclusive. */
  endIndex: number;
  topSpacerPx: number;
  bottomSpacerPx: number;
}

/**
 * Fixed-height windowing math: given how far the table is scrolled, returns
 * only the row indices that need to be mounted (visible viewport + overscan
 * buffer on each side), plus spacer heights that keep the scrollbar/scroll
 * position honest for the full `total` row count. Mounted row count never
 * exceeds `ceil(viewportHeight / rowHeight) + 2*overscan`, regardless of how
 * large `total` grows (thousands of alerts stay bounded DOM).
 */
export function computeVisibleRowRange(
  scrollTop: number,
  total: number,
  rowHeight: number,
  viewportHeight: number,
  overscan: number,
): VisibleRowRange {
  if (total <= 0 || rowHeight <= 0) {
    return { startIndex: 0, endIndex: 0, topSpacerPx: 0, bottomSpacerPx: 0 };
  }
  const firstVisible = Math.floor(Math.max(0, scrollTop) / rowHeight);
  const visibleRowCount = Math.ceil(viewportHeight / rowHeight);
  const startIndex = Math.max(0, firstVisible - overscan);
  const endIndex = Math.min(total, firstVisible + visibleRowCount + overscan);
  return {
    startIndex,
    endIndex,
    topSpacerPx: startIndex * rowHeight,
    bottomSpacerPx: (total - endIndex) * rowHeight,
  };
}

function StrategyFilterDropdown({
  enabledStrategies,
  counts,
  onToggle,
  onClose,
  configColors,
  filterableStrategies,
}: {
  enabledStrategies: Set<number>;
  counts: Record<number, number>;
  onToggle: (id: number) => void;
  onClose: () => void;
  configColors: Record<number, string>;
  filterableStrategies: StrategyMeta[];
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
          checked={
            filterableStrategies.length > 0
            && filterableStrategies.every(s => enabledStrategies.has(s.id))
          }
          onChange={() => {
            const allOn = filterableStrategies.every(s => enabledStrategies.has(s.id));
            filterableStrategies.forEach(s => {
              if (allOn === enabledStrategies.has(s.id)) onToggle(s.id);
            });
          }}
        />
        <span>Select / Unselect All</span>
      </label>
      {filterableStrategies.map(s => {
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
  /** Strategies shown in the column filter (defaults: all except Former). */
  filterableStrategies?: StrategyMeta[];
  showStrategyFilter?: boolean;
  emptyWaiting?: string;
  emptyConnecting?: string;
}

/** Bounded HOD table: fixed-window virtualization mounts only the rows in
 * view (+ overscan), so DOM size stays flat whether there are 50 or 50,000
 * alerts. */
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
  filterableStrategies = STRATEGY_META.filter(
    s => s.id !== HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
  ),
  showStrategyFilter = true,
  emptyWaiting = HOD_MOMO_EMPTY_WAITING,
  emptyConnecting = HOD_MOMO_EMPTY_CONNECTING,
}: HodMomoAlertTableProps) {
  const [showFilterDropdown, setShowFilterDropdown] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rafIdRef = useRef<number | null>(null);
  const pendingScrollTopRef = useRef(0);
  const empty = alerts.length === 0;
  // Always reserve the full 30-row scanner window (like Gappers/Gainers height),
  // even when only a few alerts have fired — shrinking to 1 row made the table look broken.
  const viewportHeight = HOD_MOMO_VISIBLE_ROWS * HOD_MOMO_ROW_HEIGHT_PX;
  const { startIndex, endIndex, topSpacerPx, bottomSpacerPx } = computeVisibleRowRange(
    scrollTop,
    alerts.length,
    HOD_MOMO_ROW_HEIGHT_PX,
    viewportHeight,
    HOD_MOMO_OVERSCAN_ROWS,
  );
  const renderedAlerts = alerts.slice(startIndex, endIndex);

  useEffect(() => {
    setScrollTop(0);
    scrollRef.current?.scrollTo({ top: 0 });
  }, [visibleStrategies]);

  useEffect(() => {
    if (empty) setScrollTop(0);
  }, [empty]);

  // Coalesce native scroll events (which can fire far faster than 60fps) to
  // at most one windowing recompute per animation frame — avoids a state
  // update (and full row-range recalculation) on every single scroll tick.
  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) cancelAnimationFrame(rafIdRef.current);
    };
  }, []);

  const handleScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    pendingScrollTopRef.current = event.currentTarget.scrollTop;
    if (rafIdRef.current !== null) return;
    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = null;
      setScrollTop(pendingScrollTopRef.current);
    });
  }, []);

  return (
    <div
      className="table-wrapper hod-table-wrapper"
      ref={scrollRef}
      onScroll={handleScroll}
      data-rendered-count={renderedAlerts.length}
      data-total-count={alerts.length}
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
                onClick={
                  key === 'strategy' && showStrategyFilter
                    ? () => setShowFilterDropdown(x => !x)
                    : undefined
                }
                style={
                  key === 'strategy' && showStrategyFilter
                    ? { cursor: 'pointer', userSelect: 'none' }
                    : undefined
                }
              >
                <span className="th-inner">
                  {label}
                  {key === 'strategy' && showStrategyFilter && (
                    <span className="hod-filter-icon">▾</span>
                  )}
                </span>
                {key === 'strategy' && showStrategyFilter && showFilterDropdown && (
                  <StrategyFilterDropdown
                    enabledStrategies={visibleStrategies}
                    counts={strategyCounts}
                    onToggle={onToggleStrategy}
                    onClose={() => setShowFilterDropdown(false)}
                    configColors={configColors}
                    filterableStrategies={filterableStrategies}
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
                {connected ? emptyWaiting : emptyConnecting}
              </td>
            </tr>
          ) : (
            <>
              {topSpacerPx > 0 && (
                <tr aria-hidden="true" style={{ height: topSpacerPx }}>
                  <td colSpan={HOD_MOMO_COLUMNS.length} style={{ padding: 0, border: 'none' }} />
                </tr>
              )}
              {renderedAlerts.map(alert => (
                <HodMomoAlertRow
                  key={alert.id}
                  alert={alert}
                  configColors={configColors}
                  selected={selectedSymbol === alert.ticker}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                  consolidationSec={consolidationSec}
                />
              ))}
              {bottomSpacerPx > 0 && (
                <tr aria-hidden="true" style={{ height: bottomSpacerPx }}>
                  <td colSpan={HOD_MOMO_COLUMNS.length} style={{ padding: 0, border: 'none' }} />
                </tr>
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}
