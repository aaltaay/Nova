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

/** Bounded HOD table that incrementally mounts rows in fixed-size batches. */
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomTriggeredRef = useRef(false);
  const viewportHeight = HOD_MOMO_VISIBLE_ROWS * HOD_MOMO_ROW_HEIGHT_PX;
  const empty = alerts.length === 0;
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
    if (
      !bottomTriggeredRef.current
      && renderedCount < alerts.length
    ) {
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
              {renderedAlerts.map(alert => (
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
  );
}
