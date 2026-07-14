import { useMemo, useRef, useState } from 'react';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { HOD_MOMO_COLUMNS, HOD_MOMO_EMPTY_CONNECTING, HOD_MOMO_EMPTY_WAITING, STRATEGY_META, STRATEGY_META_MAP } from '../constants';
import type { AlertObject } from './types';
import type { UseHodMomoConfigReturn } from './useHodMomoConfig';
import { HodMomoDebugPanel } from './HodMomoDebugPanel';

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtClock(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
    });
  } catch {
    return iso;
  }
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

// ── Strategy pill ─────────────────────────────────────────────────────────────

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

// ── Consolidated badge ────────────────────────────────────────────────────────

function ConsolidationBadge({ count, seconds }: { count: number; seconds: number }) {
  return (
    <span className="hod-consolidation-badge" title={`${count} alerts within ${seconds}s`}>
      {count} in {seconds}s
    </span>
  );
}

// ── Alert row ─────────────────────────────────────────────────────────────────

function AlertRow({
  alert,
  strategyColorOverride,
  selected,
  onSelect,
  onOpenTrading,
  consolidationSec,
}: {
  alert: AlertObject;
  strategyColorOverride?: string;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  consolidationSec: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const isConsolidated = alert.consolidation_count > 1;

  return (
    <>
      <tr className={selected ? 'row-selected' : ''}>
        {HOD_MOMO_COLUMNS.map(([key]) => {
          switch (key) {
            case 'time':
              return (
                <td key={key} className="hod-time-cell">
                  <span>{fmtClock(alert.timestamp)}</span>
                  {isConsolidated && (
                    <button
                      className="hod-expand-btn"
                      onClick={() => setExpanded(x => !x)}
                      title={expanded ? 'Collapse' : 'Expand consolidated alerts'}
                    >
                      <ConsolidationBadge count={alert.consolidation_count} seconds={Math.round(consolidationSec)} />
                    </button>
                  )}
                </td>
              );
            case 'symbol':
              return (
                <td key={key}>
                  <SymbolSelectButton
                    symbol={alert.ticker}
                    selected={selected}
                    onSelect={onSelect}
                    onOpenTrading={onOpenTrading}
                  />
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
                      {alert.rvol_source === 'yfinance' && (
                        <span
                          className="hod-rvol-badge yf"
                          title="RVOL from yfinance consolidated data (IEX free tier)"
                        >
                          YF
                        </span>
                      )}
                    </span>
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
            case 'strategy':
              return (
                <td key={key}>
                  <StrategyPill
                    strategyId={alert.strategy_id}
                    strategyName={alert.strategy_name}
                    colorOverride={strategyColorOverride}
                  />
                </td>
              );
            default:
              return <td key={key}><span className="na-muted">—</span></td>;
          }
        })}
      </tr>
      {expanded && isConsolidated && (
        <tr className="hod-expanded-row">
          <td colSpan={HOD_MOMO_COLUMNS.length} className="hod-expanded-cell">
            <div className="hod-expanded-inner">
              <span className="hod-expanded-label">Consolidated alerts:</span>
              <span>{fmtClock(alert.timestamp)} — {alert.strategy_name}</span>
              {alert.consolidated_ids.map((cid, i) => (
                <span key={i} className="hod-consolidated-id">{cid}</span>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Strategy filter dropdown ──────────────────────────────────────────────────

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
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div className="hod-filter-dropdown" ref={ref}>
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

// ── Sub-panel tab strip ───────────────────────────────────────────────────────

type SubPanel = number | 'main' | 'debug';

function SubPanelStrip({
  activeSubPanel,
  onSelect,
  counts,
  configColors,
}: {
  activeSubPanel: SubPanel;
  onSelect: (panel: SubPanel) => void;
  counts: Record<number, number>;
  configColors: Record<number, string>;
}) {
  return (
    <div className="hod-subpanel-strip">
      <button
        className={`hod-subpanel-btn${activeSubPanel === 'main' ? ' active' : ''}`}
        onClick={() => onSelect('main')}
      >
        Main feed
      </button>
      {STRATEGY_META.map(s => {
        const color = configColors[s.id] || s.color;
        const count = counts[s.id] ?? 0;
        return (
          <button
            key={s.id}
            className={`hod-subpanel-btn${activeSubPanel === s.id ? ' active' : ''}`}
            style={activeSubPanel === s.id ? { borderBottomColor: color } : {}}
            onClick={() => onSelect(s.id)}
            title={s.name}
          >
            <span className="hod-subpanel-dot" style={{ background: color }} />
            <span className="hod-subpanel-label">{s.name}</span>
            {count > 0 && <span className="hod-subpanel-count">{count}</span>}
          </button>
        );
      })}
      <button
        className={`hod-subpanel-btn hod-subpanel-debug${activeSubPanel === 'debug' ? ' active' : ''}`}
        onClick={() => onSelect('debug')}
        title="Debug panel — gate counters, decisions, symbol inspector"
      >
        🔍 Debug
      </button>
    </div>
  );
}

// ── Main HOD Momo Tab ─────────────────────────────────────────────────────────

interface HodMomoTabProps {
  alerts: AlertObject[];
  connected: boolean;
  config: UseHodMomoConfigReturn;
  selectedSymbol: string | null;
  onSelectSymbol: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
  onOpenSettings: () => void;
  dataFeed?: string;
}

export function HodMomoTab({
  alerts,
  connected,
  config,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onOpenSettings,
  dataFeed,
}: HodMomoTabProps) {
  const [activeSubPanel, setActiveSubPanel] = useState<SubPanel>('main');
  const [showFilterDropdown, setShowFilterDropdown] = useState(false);
  // Which strategy IDs are currently visible (all enabled by default)
  const [visibleStrategies, setVisibleStrategies] = useState<Set<number>>(
    new Set(STRATEGY_META.map(s => s.id)),
  );

  const consolidationSec = config.state.master.consolidation_sec;

  // Build color override map from loaded configs
  const configColors = useMemo<Record<number, string>>(() => {
    const result: Record<number, string> = {};
    for (const [sid, cfg] of Object.entries(config.state.strategies)) {
      result[Number(sid)] = cfg.color;
    }
    return result;
  }, [config.state.strategies]);

  // Count alerts per strategy
  const strategyCounts = useMemo<Record<number, number>>(() => {
    const c: Record<number, number> = {};
    for (const a of alerts) {
      c[a.strategy_id] = (c[a.strategy_id] ?? 0) + 1;
    }
    return c;
  }, [alerts]);

  // Filtered + sub-panel sliced alerts
  const visibleAlerts = useMemo(() => {
    let filtered = alerts.filter(a => visibleStrategies.has(a.strategy_id));
    if (activeSubPanel !== 'main') {
      filtered = filtered.filter(a => a.strategy_id === activeSubPanel);
    }
    return filtered;
  }, [alerts, visibleStrategies, activeSubPanel]);

  function toggleStrategy(id: number) {
    setVisibleStrategies(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="hod-momo-tab">
      {/* Header bar */}
      <div className="hod-header-bar">
        <div className="hod-header-left">
          <span className={`hod-connection-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span className="hod-header-title">HOD Momo Scanner</span>
          <span className="hod-alert-count">{alerts.length} alerts today</span>
        </div>
        <div className="hod-header-right">
          <button className="hod-settings-btn" onClick={onOpenSettings} title="Configure strategies">
            ⚙ Configure
          </button>
        </div>
      </div>

      {/* IEX free tier RVOL source banner */}
      {dataFeed === 'iex' && (
        <div className="hod-iex-banner">
          <span className="hod-iex-banner-icon">ⓘ</span>
          <span>
            <strong>IEX Free Tier</strong> — RVOL sourced from yfinance (consolidated).
            Upgrade to SIP for real-time RVOL.
          </span>
        </div>
      )}

      {/* Sub-panel strip */}
      <SubPanelStrip
        activeSubPanel={activeSubPanel}
        onSelect={setActiveSubPanel}
        counts={strategyCounts}
        configColors={configColors}
      />

      {/* Debug panel — shown instead of the alert table */}
      {activeSubPanel === 'debug' && (
        <HodMomoDebugPanel />
      )}

      {/* Alert table — hidden when debug panel is active */}
      {activeSubPanel !== 'debug' && (
        <div className="table-wrapper hod-table-wrapper">
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
                        onToggle={toggleStrategy}
                        onClose={() => setShowFilterDropdown(false)}
                        configColors={configColors}
                      />
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleAlerts.length === 0 ? (
                <tr>
                  <td colSpan={HOD_MOMO_COLUMNS.length} className="hod-empty-cell">
                    {connected
                      ? HOD_MOMO_EMPTY_WAITING
                      : HOD_MOMO_EMPTY_CONNECTING}
                  </td>
                </tr>
              ) : (
                visibleAlerts.map(alert => (
                  <AlertRow
                    key={alert.id}
                    alert={alert}
                    strategyColorOverride={configColors[alert.strategy_id]}
                    selected={selectedSymbol === alert.ticker}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    consolidationSec={consolidationSec}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
