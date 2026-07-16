import type { Counters } from './hodMomoDebugTypes';

export function CountersCard({ data, age }: { data: Counters | null; age: number }) {
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
