/**
 * ArchiveRewind — P9 no-hindsight rewind (2026-07-15 hardening).
 *
 * Loads a no-hindsight decision timeline for a local cold-archive day via
 * GET /api/archive/walk/{day} — each step's decisions only ever saw bars up
 * to that step's as_of_ts (backend/archive/replay.py::walk_day). The slider
 * scrubs through that timeline: "what would Nova OS have decided at this
 * moment, knowing only what it knew then?" Never shows whole-day hindsight.
 */
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

interface WalkStep {
  as_of_ts: number;
  as_of_iso: string;
  decisions: ReplayDecision[];
  errors?: { symbol: string; error: string }[];
}

interface WalkResponse {
  session_date: string;
  step_min?: number;
  step_count?: number;
  steps?: WalkStep[];
  hindsight?: boolean;
  error?: string;
}

const STEP_MIN_MINUTES = 5;
const SYMBOL_LIMIT = 10;

export function ArchiveRewind({ active }: { active: boolean }) {
  const [days, setDays] = useState<string[]>([]);
  const [selected, setSelected] = useState('');
  const [walk, setWalk] = useState<WalkResponse | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
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

  async function loadTimeline() {
    if (!selected) return;
    setLoading(true);
    setWalk(null);
    try {
      const params = new URLSearchParams({
        limit: String(SYMBOL_LIMIT),
        step_min: String(STEP_MIN_MINUTES),
      });
      const res = await fetch(`${API_BASE_URL}/api/archive/walk/${encodeURIComponent(selected)}?${params}`);
      const data = (await res.json()) as WalkResponse;
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setWalk(data);
      // Default to the final (most-informed) step; rewind moves backward.
      setStepIndex(Math.max(0, (data.steps?.length ?? 1) - 1));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (!active) return null;

  const steps = walk?.steps ?? [];
  const currentStep = steps[stepIndex];

  return (
    <div className="archive-rewind" style={{ padding: '12px 0' }}>
      <div className="watchlist-description">
        No-hindsight rewind (P9). Each step below only saw bars up to that
        moment — no lookahead. Prefer CLI for deep review:{' '}
        <code>py tools/nova_os_replay.py walk 2026-07-10</code>.
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
          <button type="button" disabled={!selected || loading} onClick={() => void loadTimeline()}>
            {loading ? 'Loading…' : 'Load timeline'}
          </button>
          <button type="button" onClick={() => void loadDays()}>Refresh days</button>
        </div>
      )}
      {steps.length > 0 && (
        <div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <button
              type="button"
              disabled={stepIndex <= 0}
              onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              aria-label="Rewind one step"
            >
              ◀ Rewind
            </button>
            <input
              type="range"
              min={0}
              max={steps.length - 1}
              value={stepIndex}
              onChange={(e) => setStepIndex(Number(e.target.value))}
              aria-label="Archive rewind position"
              style={{ flex: 1 }}
            />
            <button
              type="button"
              disabled={stepIndex >= steps.length - 1}
              onClick={() => setStepIndex((i) => Math.min(steps.length - 1, i + 1))}
              aria-label="Advance one step"
            >
              Forward ▶
            </button>
          </div>
          <div style={{ marginBottom: 8 }}>
            As of <strong>{currentStep?.as_of_iso ?? '—'}</strong> · step {stepIndex + 1} / {steps.length} ·
            no lookahead past this moment
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {(currentStep?.decisions || []).map((d) => (
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
