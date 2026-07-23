import { memo } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import {
  HOD_MOMO_COLUMNS,
  HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
  HOD_MOMO_MAX_INLINE_STRATEGY_PILLS,
  HOD_MOMO_ROW_HEIGHT_PX,
  STRATEGY_META_MAP,
} from '../constants';
import type { AlertObject } from './types';

function fmtClock(iso: string, createdTs?: number): string {
  let d: Date | null = null;
  if (iso) {
    const parsed = new Date(iso);
    if (!Number.isNaN(parsed.getTime())) d = parsed;
  }
  if (!d && typeof createdTs === 'number' && createdTs > 0) {
    // Backend may send created_ts in unix seconds; accept ms if already large.
    const ms = createdTs > 1e12 ? createdTs : createdTs * 1000;
    d = new Date(ms);
  }
  if (!d || Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return '—';
  return `$${v.toFixed(2)}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function fmtVolume(v: number | null | undefined): string {
  if (v == null) return '—';
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

function StrategyPill({
  strategyId,
  strategyName,
  colorOverride,
}: {
  strategyId: number;
  strategyName: string;
  colorOverride?: string;
}) {
  const meta = STRATEGY_META_MAP[strategyId];
  const color = colorOverride || meta?.color || '#888';
  return (
    <span
      className="hod-strategy-pill"
      style={{ background: color + '33', color, border: `1px solid ${color}66` }}
      title={strategyName}
    >
      {strategyName}
    </span>
  );
}

function ConsolidationBadge({ count, seconds }: { count: number; seconds: number }) {
  return (
    <span className="hod-consolidation-badge" title={`${count} alerts within ${seconds}s`}>
      ({count} in {seconds}sec)
    </span>
  );
}

export const HodMomoAlertRow = memo(function HodMomoAlertRow({
  alert,
  configColors = {},
  selected,
  onSelect,
  onOpenTrading,
}: {
  alert: AlertObject;
  configColors?: Record<number, string>;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  consolidationSec?: number;
}) {
  const isConsolidated = alert.consolidation_count > 1;
  const spanSec = Math.max(1, alert.consolidation_span_sec ?? 1);
  const consolidatedTitle = isConsolidated
    ? `${alert.consolidation_count} in ${spanSec}sec`
    : undefined;
  const strategyTags = (
    alert.strategies?.length
      ? alert.strategies
      : [{ id: alert.strategy_id, name: alert.strategy_name }]
  ).filter(tag => tag.id !== HOD_MOMO_FORMER_MOMO_STRATEGY_ID);

  return (
    <SelectableTableRow
      symbol={alert.ticker}
      selected={selected}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
      className="hod-alert-row"
      style={{ height: HOD_MOMO_ROW_HEIGHT_PX }}
    >
      {HOD_MOMO_COLUMNS.map(([key]) => {
        switch (key) {
          case 'time':
            return (
              <td key={key} className="hod-time-cell">
                <span>{fmtClock(alert.timestamp, alert.created_ts)}</span>
              </td>
            );
          case 'symbol':
            return (
              <td key={key} className="hod-symbol-td">
                <div className="hod-symbol-cell">
                  <SymbolSelectButton
                    symbol={alert.ticker}
                    selected={selected}
                    onSelect={onSelect}
                    onOpenTrading={onOpenTrading}
                  />
                  {isConsolidated && (
                    <span className="hod-symbol-burst" title={consolidatedTitle}>
                      <ConsolidationBadge
                        count={alert.consolidation_count}
                        seconds={spanSec}
                      />
                    </span>
                  )}
                </div>
              </td>
            );
          case 'price':
            return <td key={key}>{fmtPrice(alert.price)}</td>;
          case 'change_pct':
            return (
              <td key={key}>
                <span className={alert.change_pct >= 0 ? 'positive' : 'negative'}>
                  {fmtPct(alert.change_pct)}
                </span>
              </td>
            );
          case 'rvol':
            return (
              <td key={key}>
                {alert.rvol != null ? (
                  <span className="hod-rvol-cell">
                    {alert.rvol.toFixed(2)}x
                    {(alert.rvol_source === 'yfinance' || alert.rvol_source === 'yfinance_pace') && (
                      <span
                        className="hod-rvol-badge yf"
                        title="Pace RVOL from yfinance average volume"
                      >
                        YF
                      </span>
                    )}
                  </span>
                ) : <span className="na-muted">—</span>}
              </td>
            );
          case 'rvol_5min':
            return (
              <td key={key}>
                {alert.rvol_5min != null ? (
                  <span className="hod-rvol-cell">{alert.rvol_5min.toFixed(2)}x</span>
                ) : <span className="na-muted">—</span>}
              </td>
            );
          case 'float':
            return (
              <td key={key}>
                {alert.float_shares != null ? fmtVolume(alert.float_shares) : <span className="na-muted">—</span>}
              </td>
            );
          case 'gap_pct':
            return (
              <td key={key}>
                {alert.gap_pct != null ? (
                  <span className={alert.gap_pct >= 0 ? 'positive' : 'negative'}>
                    {fmtPct(alert.gap_pct)}
                  </span>
                ) : <span className="na-muted">—</span>}
              </td>
            );
          case 'volume':
            return <td key={key}>{fmtVolume(alert.volume)}</td>;
          case 'strategy': {
            const visibleTags = strategyTags.slice(0, HOD_MOMO_MAX_INLINE_STRATEGY_PILLS);
            const overflowTags = strategyTags.slice(HOD_MOMO_MAX_INLINE_STRATEGY_PILLS);
            return (
              <td key={key} className="hod-strategy-cell">
                {strategyTags.length === 0 ? (
                  <span className="na-muted">—</span>
                ) : (
                  <div
                    className="hod-strategy-pills"
                    title={strategyTags.map(s => s.name).join(' · ')}
                  >
                    {visibleTags.map(tag => (
                      <StrategyPill
                        key={tag.id}
                        strategyId={tag.id}
                        strategyName={tag.name}
                        colorOverride={configColors[tag.id]}
                      />
                    ))}
                    {overflowTags.length > 0 && (
                      <span
                        className="hod-strategy-pill-more"
                        title={overflowTags.map(t => t.name).join(' · ')}
                      >
                        +{overflowTags.length}
                      </span>
                    )}
                  </div>
                )}
              </td>
            );
          }
          default:
            return <td key={key}><span className="na-muted">—</span></td>;
        }
      })}
    </SelectableTableRow>
  );
});
