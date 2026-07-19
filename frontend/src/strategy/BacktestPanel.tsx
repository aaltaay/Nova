/**
 * BacktestPanel — Phase E: run Nova-native backtest on archived 1m bars.
 * Pick cold day + setup, POST /api/backtest/run, show metrics + honesty banner.
 */
import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';

interface BacktestDaysResponse {
  days: string[];
  count: number;
}

interface TradeMetrics {
  trade_count: number;
  win_rate: number | null;
  profit_factor: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  max_drawdown_pct: number | null;
  total_pnl_dollars: number;
  total_pnl_r: number;
}

interface HonestyLabels {
  bar_resolution: string;
  spread_modeled: boolean;
  hindsight: boolean;
  candidate_source?: string;
  fill_model?: string;
  exit_model?: string;
}

interface BacktestRunResponse {
  ok: boolean;
  session_date: string;
  setup: string;
  trade_count: number;
  metrics: TradeMetrics;
  honesty: HonestyLabels;
  trades: { symbol: string; setup: string; pnl_dollars: number; exit_reason: string }[];
  error?: string;
  note?: string;
}

const SETUP_OPTIONS = [
  { value: 'all', label: 'All setups' },
  { value: 'gap_and_go', label: 'Gap and Go' },
  { value: 'bull_flag', label: 'Bull Flag' },
  { value: 'abcd', label: 'ABCD' },
] as const;

function fmtMetric(v: number | null, suffix = ''): string {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(2)}${suffix}`;
}

export function BacktestPanel({ active }: { active: boolean }) {
  const [days, setDays] = useState<string[]>([]);
  const [selectedDay, setSelectedDay] = useState('');
  const [setup, setSetup] = useState<string>('all');
  const [result, setResult] = useState<BacktestRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDays = useCallback(async () => {
    if (!active) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/backtest/days`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as BacktestDaysResponse;
      const list = data.days || [];
      setDays(list);
      setSelectedDay((prev) => prev || (list.length ? list[list.length - 1] : ''));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [active]);

  useEffect(() => {
    void loadDays();
  }, [loadDays]);

  async function runBacktest() {
    if (!selectedDay) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_date: selectedDay, setup }),
      });
      const data = (await res.json()) as BacktestRunResponse & { detail?: string };
      if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
      setResult(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (!active) return null;

  const m = result?.metrics;

  return (
    <div className="backtest-panel" style={{ padding: '12px 0' }}>
      <div className="watchlist-description">
        Nova-native backtest on archived 1m bars. No vectorbt at runtime; no orders placed.
        Signals use slice-as-of bars (no hindsight); entries fill at next bar open.
      </div>

      <div className="backtest-controls" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <label>
          Session day{' '}
          <select value={selectedDay} onChange={e => setSelectedDay(e.target.value)} disabled={!days.length}>
            {!days.length && <option value="">No cold days</option>}
            {days.map(d => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <label>
          Setup{' '}
          <select value={setup} onChange={e => setSetup(e.target.value)}>
            {SETUP_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => void runBacktest()} disabled={loading || !selectedDay}>
          {loading ? 'Running…' : 'Run backtest'}
        </button>
      </div>

      {error && <div className="empty-state">{error}</div>}

      {result && (
        <>
          <div
            className="backtest-honesty-banner"
            style={{
              padding: '8px 12px',
              marginBottom: '12px',
              border: '1px solid var(--border-muted, #444)',
              borderRadius: '4px',
              fontSize: '0.9em',
            }}
          >
            <strong>Honesty:</strong>{' '}
            {result.honesty.bar_resolution} bars · spread modeled:{' '}
            {result.honesty.spread_modeled ? 'yes' : 'no'} · hindsight:{' '}
            {result.honesty.hindsight ? 'yes' : 'no'}
            {result.note && <div style={{ marginTop: '4px', opacity: 0.85 }}>{result.note}</div>}
          </div>

          {m && (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Trades</th>
                    <th>Win rate</th>
                    <th>Profit factor</th>
                    <th>Avg win</th>
                    <th>Avg loss</th>
                    <th>Max DD %</th>
                    <th>Total P&amp;L $</th>
                    <th>Total R</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{m.trade_count}</td>
                    <td>{fmtMetric(m.win_rate !== null ? m.win_rate * 100 : null, '%')}</td>
                    <td>{fmtMetric(m.profit_factor)}</td>
                    <td>{fmtMetric(m.avg_win, '$')}</td>
                    <td>{fmtMetric(m.avg_loss, '$')}</td>
                    <td>{fmtMetric(m.max_drawdown_pct, '%')}</td>
                    <td>{fmtMetric(m.total_pnl_dollars, '$')}</td>
                    <td>{fmtMetric(m.total_pnl_r, 'R')}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {result.trades.length > 0 && (
            <div className="table-wrapper" style={{ marginTop: '12px' }}>
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Setup</th>
                    <th>P&amp;L $</th>
                    <th>Exit</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={`${t.symbol}-${i}`}>
                      <td>{t.symbol}</td>
                      <td>{t.setup}</td>
                      <td className={t.pnl_dollars >= 0 ? 'positive' : 'negative'}>
                        {t.pnl_dollars.toFixed(2)}
                      </td>
                      <td>{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
