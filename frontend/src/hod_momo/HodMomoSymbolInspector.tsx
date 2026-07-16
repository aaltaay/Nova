import { useState } from 'react';
import { API_BASE_URL } from '../constants';
import { fmtNum, fmtTs, fmtVol, truncate } from './hodMomoDebugFormat';
import type { SymbolInspect } from './hodMomoDebugTypes';

const API = `${API_BASE_URL}/api`;

export function SymbolInspector() {
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
