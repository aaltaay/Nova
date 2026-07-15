/** ArchiveRewind — minimal P9 stub: list local cold days + optional replay summary. */
import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';

interface ArchiveDaysResponse {
  days: string[];
  count: number;
}

interface ReplayDecision {
  symbol: string;
  decision: string;
  confidence?: number;
  reason_codes?: string[];
}

interface ReplayResponse {
  session_date: string;
  decision_count?: number;
  decisions?: ReplayDecision[];
  error?: string;
  note?: string;
}

export function ArchiveRewind({ active }: { active: boolean }) {
  const [days, setDays] = useState<string[]>([]);
  const [selected, setSelected] = useState('');
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDays = useCallback(async () => {
    if (!active) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/archive/days`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ArchiveDaysResponse;
      setDays(data.days || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [active]);

  useEffect(() => {
    void loadDays();
  }, [loadDays]);

  async function runReplay() {
    if (!selected) return;
    setLoading(true);
    setReplay(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/archive/replay/${encodeURIComponent(selected)}?limit=10`);
      const data = (await res.json()) as ReplayResponse;
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setReplay(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (!active) return null;

  return (
    <div className="archive-rewind" style={{ padding: '12px 0' }}>
      <div className="watchlist-description">
        Local cold-archive days (P9). Replay runs <code>decide(record=False)</code> —
        no receipts, no orders. Prefer CLI for deep review:{' '}
        <code>py tools/nova_os_replay.py</code>.
      </div>
      {error && <div className="empty-state">{error}</div>}
      {days.length === 0 && !error ? (
        <div className="empty-state">No local cold days yet. Compact a finished session first.</div>
      ) : (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
          <label>
            Day{' '}
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              aria-label="Archive session date"
            >
              <option value="">Select…</option>
              {days.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </label>
          <button type="button" disabled={!selected || loading} onClick={() => void runReplay()}>
            {loading ? 'Replaying…' : 'Replay'}
          </button>
          <button type="button" onClick={() => void loadDays()}>Refresh days</button>
        </div>
      )}
      {replay && (
        <div>
          <div style={{ marginBottom: 8 }}>
            {replay.session_date}: {replay.decision_count ?? 0} decisions
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {(replay.decisions || []).slice(0, 10).map((d) => (
              <li key={d.symbol} style={{ marginBottom: 4 }}>
                <strong>{d.symbol}</strong> → {d.decision}
                {d.confidence != null ? ` · conf ${d.confidence}` : ''}
                {d.reason_codes?.length ? ` · ${d.reason_codes.slice(0, 3).join(', ')}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
