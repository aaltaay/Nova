/** The bot's timeline: what it proposed, fired, was refused, and who changed it (bot audit stream). */
import { useState } from 'react';
import { ACTIVITY_FILTER_LABELS, ACTIVITY_FILTERS, activityLines, type ActivityFilter } from './botActivityLines';
import type { BotAuditEntry } from './types';

function clock(ts: number): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
}

export function BotActivity({ audit }: { audit: BotAuditEntry[] }) {
  const [filter, setFilter] = useState<ActivityFilter>('all');
  const lines = activityLines(audit, filter);
  return (
    <section className="bots-card" data-testid="bots-activity">
      <header className="bots-card__head">
        <h3>Activity</h3>
        <div className="bots-chips" role="group" aria-label="Activity filter">
          {ACTIVITY_FILTERS.map(f => (
            <button key={f} type="button" className={`wl-fchip${filter === f ? ' is-on' : ''}`} aria-pressed={filter === f}
              onClick={() => setFilter(f)}>
              {ACTIVITY_FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </header>
      {lines.length === 0 ? (
        <p className="bots-empty">Nothing yet.</p>
      ) : (
        <ul className="bots-timeline">
          {lines.map(l => (
            <li key={l.key}>
              <span className="bots-timeline__t">{clock(l.ts)}</span>
              <span className={`bots-timeline__tag bots-timeline__tag--${l.tone}`}>{l.tag}</span>
              <span className="bots-timeline__text">{l.text}</span>
              {l.note ? <span className="bots-timeline__note">{l.note}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
