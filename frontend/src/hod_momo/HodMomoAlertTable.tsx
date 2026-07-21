import { useEffect, useRef, useState, type UIEvent } from 'react';
import {
  HOD_MOMO_COLUMNS,
  HOD_MOMO_EMPTY_CONNECTING,
  HOD_MOMO_EMPTY_WAITING,
  HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
  HOD_MOMO_HEADER_HEIGHT_PX,
  HOD_MOMO_LOAD_MORE_THRESHOLD_PX,
  HOD_MOMO_RENDER_BATCH_SIZE,
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_VISIBLE_ROWS,
  STRATEGY_META,
  type StrategyMeta,
} from '../constants';
import type { AlertObject } from './types';
import { HodMomoAlertRow } from './HodMomoAlertRow';

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

export function nextHodMomoRenderedCount(current: number, total: number): number {
  return Math.min(current + HOD_MOMO_RENDER_BATCH_SIZE, total);
}

/** Bounded HOD table that mounts rows only in fixed-size bottom-triggered batches. */
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
  const [renderedCount, setRenderedCount] = useState(HOD_MOMO_RENDER_BATCH_SIZE);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomTriggeredRef = useRef(false);
  const empty = alerts.length === 0;
  // Always reserve the full 30-row scanner window (like Gappers/Gainers height),
  // even when only a few alerts have fired — shrinking to 1 row made the table look broken.
  const viewportHeight = HOD_MOMO_VISIBLE_ROWS * HOD_MOMO_ROW_HEIGHT_PX;
  const renderedAlerts = alerts.slice(0, renderedCount);

  useEffect(() => {
    setRenderedCount(HOD_MOMO_RENDER_BATCH_SIZE);
    bottomTriggeredRef.current = false;
    scrollRef.current?.scrollTo({ top: 0 });
  }, [visibleStrategies]);

  useEffect(() => {
    if (empty) {
      setRenderedCount(HOD_MOMO_RENDER_BATCH_SIZE);
      bottomTriggeredRef.current = false;
    }
  }, [empty]);

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;

    if (distanceFromBottom > HOD_MOMO_LOAD_MORE_THRESHOLD_PX) {
      bottomTriggeredRef.current = false;
      return;
    }

    if (!bottomTriggeredRef.current && renderedCount < alerts.length) {
      bottomTriggeredRef.current = true;
      setRenderedCount(current =>
        nextHodMomoRenderedCount(current, alerts.length),
      );
    }
  }

  return (
    <div
      className="table-wrapper hod-table-wrapper"
      ref={scrollRef}
      onScroll={handleScroll}
      data-rendered-count={renderedAlerts.length}
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
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}
