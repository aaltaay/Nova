import { useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  HOD_MOMO_COLUMNS,
  HOD_MOMO_EMPTY_CONNECTING,
  HOD_MOMO_EMPTY_WAITING,
  HOD_MOMO_HEADER_HEIGHT_PX,
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_VIRTUAL_OVERSCAN,
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

/**
 * HOD alert table virtualized with @tanstack/react-virtual.
 * Continuous scroll over the full day list; only the viewport + overscan
 * rows are mounted (library handles windowing as the user scrolls).
 */
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const viewportHeight = HOD_MOMO_VISIBLE_ROWS * HOD_MOMO_ROW_HEIGHT_PX;

  const rowVirtualizer = useVirtualizer({
    count: alerts.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => HOD_MOMO_ROW_HEIGHT_PX,
    overscan: HOD_MOMO_VIRTUAL_OVERSCAN,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualRows.length > 0
      ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
      : 0;

  const empty = alerts.length === 0;

  return (
    <div
      className="table-wrapper hod-table-wrapper hod-table-virtual"
      ref={scrollRef}
      style={{ height: viewportHeight + HOD_MOMO_HEADER_HEIGHT_PX }}
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
              {paddingTop > 0 && (
                <tr aria-hidden="true" className="hod-virtual-spacer">
                  <td
                    colSpan={HOD_MOMO_COLUMNS.length}
                    style={{ height: paddingTop, padding: 0, border: 'none' }}
                  />
                </tr>
              )}
              {virtualRows.map(virtualRow => {
                const alert = alerts[virtualRow.index];
                return (
                  <HodMomoAlertRow
                    key={alert.id}
                    alert={alert}
                    strategyColorOverride={configColors[alert.strategy_id]}
                    selected={selectedSymbol === alert.ticker}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    consolidationSec={consolidationSec}
                  />
                );
              })}
              {paddingBottom > 0 && (
                <tr aria-hidden="true" className="hod-virtual-spacer">
                  <td
                    colSpan={HOD_MOMO_COLUMNS.length}
                    style={{ height: paddingBottom, padding: 0, border: 'none' }}
                  />
                </tr>
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}
