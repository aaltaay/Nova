import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import {
  RecentDecisionsTable,
  SnapsTable,
  type DebugDecisionRow,
  type DebugSnapRow,
} from './HodMomoDebugTables';

const API = `${API_BASE_URL}/api`;

// ── Types ─────────────────────────────────────────────────────────────────────

interface Counters {
  total_trades_seen: number;
  universe_size: number;
  snaps_populated: number;
  counters: Record<string, number>;
  session_highs_tracked: number;
  fundamentals_queue_depth: number;
}

interface SymbolInspect {
  symbol: string;
  snap: {
    price: number | null;
    rvol: number | null;
    float_shares: number | null;
    gap_pct: number | null;
    change_pct: number | null;
    volume: number | null;
    fifty_two_week_high: number | null;
    last_enriched: number;
  };
  session_high: number | null;
  decisions: Array<{
    ts: number;
    price: number;
    gate_blocked: string | null;
    strategies: Array<{ id: number; name: string; passed: boolean; blocked_by: string }>;
    would_fire: boolean;
  }>;
  would_fire_now: {
    gate: string;
    strategies: Array<{ id: number; name: string; passed: boolean; blocked_by: string }>;
  } | null;
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—';
  return v.toFixed(decimals);
}

function fmtVol(v: number | null | undefined): string {
  if (v == null) return '—';
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

// ── Counter card ──────────────────────────────────────────────────────────────

function CountersCard({ data, age }: { data: Counters | null; age: number }) {
  if (!data) return <div className="dbg-card dbg-loading">Loading counters…</div>;

  const counters = data.counters;
  const keys = Object.keys(counters).sort();

  return (
    <div className="dbg-card">
      <div className="dbg-card-title">
        Gate Counters
        <span className="dbg-age">{age < 5 ? 'live' : `${age}s ago`}</span>
      </div>
      <div className="dbg-stats-row">
        <div className="dbg-stat">
          <span className="dbg-stat-val">{data.total_trades_seen.toLocaleString()}</span>
          <span className="dbg-stat-label">trades seen</span>
        </div>
        <div className="dbg-stat">
          <span className="dbg-stat-val">{data.universe_size.toLocaleString()}</span>
          <span className="dbg-stat-label">universe</span>
        </div>
        <div className="dbg-stat">
          <span className="dbg-stat-val">{data.snaps_populated.toLocaleString()}</span>
          <span className="dbg-stat-label">snaps enriched</span>
        </div>
        <div className="dbg-stat">
          <span className="dbg-stat-val">{data.session_highs_tracked.toLocaleString()}</span>
          <span className="dbg-stat-label">session HODs</span>
        </div>
        <div className="dbg-stat">
          <span className="dbg-stat-val">{data.fundamentals_queue_depth}</span>
          <span className="dbg-stat-label">fund. queue</span>
        </div>
      </div>
      <div className="dbg-counter-list">
        {keys.map(k => (
          <div key={k} className="dbg-counter-row">
            <span className="dbg-counter-key">{k}</span>
            <span className="dbg-counter-bar-wrap">
              <span
                className="dbg-counter-bar"
                style={{ width: `${Math.min(100, (counters[k] / (data.total_trades_seen || 1)) * 100)}%` }}
              />
            </span>
            <span className="dbg-counter-val">{counters[k].toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '…' : s;
}

// ── Symbol inspector ──────────────────────────────────────────────────────────

function SymbolInspector() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SymbolInspect | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function inspect() {
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API}/hod-momo/debug/symbol/${sym}`);
      const data = await resp.json();
      setResult(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="dbg-card dbg-card-wide">
      <div className="dbg-card-title">Symbol Inspector</div>
      <div className="dbg-inspector-input">
        <input
          type="text"
          className="dbg-sym-input"
          placeholder="Ticker (e.g. AAPL)"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && inspect()}
        />
        <button className="dbg-inspect-btn" onClick={inspect} disabled={loading}>
          {loading ? '…' : 'Inspect'}
        </button>
      </div>
      {error && <div className="dbg-error">{error}</div>}
      {result && <SymbolResult data={result} />}
    </div>
  );
}

function SymbolResult({ data }: { data: SymbolInspect }) {
  const snap = data.snap;
  const wf = data.would_fire_now;

  return (
    <div className="dbg-inspector-result">
      <div className="dbg-snap-grid">
        <SnapField label="Price" value={snap.price != null ? `$${snap.price.toFixed(2)}` : '—'} />
        <SnapField label="RVOL" value={snap.rvol != null ? `${snap.rvol.toFixed(2)}x` : '—'} />
        <SnapField label="Float" value={fmtVol(snap.float_shares)} />
        <SnapField label="Gap %" value={snap.gap_pct != null ? `${snap.gap_pct.toFixed(2)}%` : '—'} />
        <SnapField label="Chg %" value={snap.change_pct != null ? `${snap.change_pct.toFixed(2)}%` : '—'} />
        <SnapField label="Volume" value={fmtVol(snap.volume)} />
        <SnapField label="52wk High" value={snap.fifty_two_week_high != null ? `$${snap.fifty_two_week_high.toFixed(2)}` : '—'} />
        <SnapField label="Session HOD" value={data.session_high != null ? `$${data.session_high.toFixed(2)}` : '—'} />
        <SnapField
          label="Last enriched"
          value={snap.last_enriched ? `${Math.round(Date.now() / 1000 - snap.last_enriched)}s ago` : 'never'}
        />
      </div>

      {wf && (
        <div className="dbg-wf">
          <div className="dbg-wf-title">Would fire now?</div>
          <div className={`dbg-wf-gate ${wf.gate === 'passed' ? 'dbg-wf-pass' : 'dbg-wf-block'}`}>
            Gate: {wf.gate}
          </div>
          {wf.gate === 'passed' && (
            <div className="dbg-strategy-list">
              {wf.strategies.map(s => (
                <div key={s.id} className={`dbg-strategy-row ${s.passed ? 'dbg-s-pass' : 'dbg-s-block'}`}>
                  <span className="dbg-s-num">{s.id}</span>
                  <span className="dbg-s-name">{s.name}</span>
                  <span className="dbg-s-reason">{s.passed ? '✓' : s.blocked_by}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="dbg-decisions-hist">
        <div className="dbg-decisions-title">Last {data.decisions.length} decisions</div>
        {data.decisions.slice().reverse().map((d, i) => (
          <div key={i} className={`dbg-dec-row ${d.gate_blocked ? 'dbg-row-blocked' : d.would_fire ? 'dbg-row-fired' : ''}`}>
            <span className="dbg-mono">{fmtTs(d.ts)}</span>
            <span>${fmtNum(d.price)}</span>
            <span className="dbg-gate">{d.gate_blocked ? truncate(d.gate_blocked, 35) : '✓ gate ok'}</span>
            {!d.gate_blocked && (
              <span className="dbg-strat-summary">
                fired: [{d.strategies.filter(s => s.passed).map(s => s.id).join(',') || 'none'}]
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function SnapField({ label, value }: { label: string; value: string }) {
  return (
    <div className="dbg-snap-field">
      <span className="dbg-snap-label">{label}</span>
      <span className="dbg-snap-val">{value}</span>
    </div>
  );
}

// ── Main debug panel ──────────────────────────────────────────────────────────

interface HodMomoDebugPanelProps {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function HodMomoDebugPanel({
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: HodMomoDebugPanelProps) {
  const [counters, setCounters] = useState<Counters | null>(null);
  const [countersAge, setCountersAge] = useState(0);
  const [countersUpdated, setCountersUpdated] = useState(0);
  const [decisions, setDecisions] = useState<DebugDecisionRow[]>([]);
  const [snaps, setSnaps] = useState<DebugSnapRow[]>([]);
  const [activeSection, setActiveSection] = useState<'counters' | 'decisions' | 'snaps' | 'inspector'>('counters');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchCounters() {
    try {
      const r = await fetch(`${API}/hod-momo/debug/counters`);
      const d = await r.json();
      setCounters(d);
      setCountersUpdated(Date.now());
    } catch { /* silent */ }
  }

  async function fetchDecisions() {
    try {
      const r = await fetch(`${API}/hod-momo/debug/recent?limit=50`);
      const d = await r.json();
      setDecisions((d.decisions ?? []).slice().reverse());
    } catch { /* silent */ }
  }

  async function fetchSnaps() {
    try {
      const r = await fetch(`${API}/hod-momo/debug/snaps?limit=50`);
      const d = await r.json();
      setSnaps(d.snaps ?? []);
    } catch { /* silent */ }
  }

  useEffect(() => {
    fetchCounters();
    fetchDecisions();
    fetchSnaps();

    timerRef.current = setInterval(() => {
      fetchCounters();
      fetchDecisions();
      fetchSnaps();
      setCountersAge(Math.round((Date.now() - countersUpdated) / 1000));
    }, 2000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update age display every second without re-fetching
  useEffect(() => {
    const t = setInterval(() => {
      setCountersAge(Math.round((Date.now() - countersUpdated) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [countersUpdated]);

  return (
    <div className="dbg-panel">
      <div className="dbg-nav">
        {(['counters', 'decisions', 'snaps', 'inspector'] as const).map(s => (
          <button
            key={s}
            className={`dbg-nav-btn${activeSection === s ? ' active' : ''}`}
            onClick={() => setActiveSection(s)}
          >
            {s === 'counters' ? '📊 Counters' :
             s === 'decisions' ? '🔍 Decisions' :
             s === 'snaps' ? '📷 Snaps' : '🔎 Inspector'}
          </button>
        ))}
      </div>

      <div className="dbg-content">
        {activeSection === 'counters' && (
          <CountersCard data={counters} age={countersAge} />
        )}
        {activeSection === 'decisions' && (
          <RecentDecisionsTable
            decisions={decisions}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={onSelectSymbol}
            onOpenTrading={onOpenTrading}
          />
        )}
        {activeSection === 'snaps' && (
          <SnapsTable
            snaps={snaps}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={onSelectSymbol}
            onOpenTrading={onOpenTrading}
          />
        )}
        {activeSection === 'inspector' && (
          <SymbolInspector />
        )}
      </div>
    </div>
  );
}
