/**
 * The bot's timeline (approved mockup v4): what it proposed, fired, was refused
 * and who changed it (the bot audit stream), beside the setup scanner's own
 * record of the day -- armed, near with the tape's read, triggered, scored.
 */
import { useState } from 'react';
import { BOTS_ACTIVITY_EMPTY, BOTS_ACTIVITY_LIMIT, BOTS_ACTIVITY_TITLE } from '../constantGroups/bots_page';
import type { SetupStoreRow } from '../setups/useSetupRows';
import { ACTIVITY_FILTER_LABELS, ACTIVITY_FILTERS, activityLines, type ActivityFilter } from './botActivityLines';
import { etClock, prose } from './botsPageFormat';
import type { BotAuditEntry } from './types';

export function BotActivity({ audit, setupRows }: { audit: BotAuditEntry[]; setupRows: readonly SetupStoreRow[] }) {
  const [filter, setFilter] = useState<ActivityFilter>('all');
  const lines = activityLines(audit, filter, BOTS_ACTIVITY_LIMIT, setupRows);
  return (
    <section className="bots-card" data-testid="bots-activity">
      <header className="bots-card__head">
        <h3>{BOTS_ACTIVITY_TITLE}</h3>
        <div className="bots-chips" role="group" aria-label="Activity filter">
          {ACTIVITY_FILTERS.map(f => (
            <button key={f} type="button" className={`bots-fchip${filter === f ? ' is-on' : ''}`} aria-pressed={filter === f}
              onClick={() => setFilter(f)}>
              {ACTIVITY_FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </header>
      {lines.length === 0 ? (
        <p className="bots-empty">{BOTS_ACTIVITY_EMPTY}</p>
      ) : (
        <ul className="bots-timeline">
          {lines.map(l => (
            <li key={l.key}>
              <span className="bots-timeline__t">{etClock(l.ts)}</span>
              <span className={`bots-timeline__dot bots-timeline__dot--${l.tone}`} aria-hidden="true" />
              <span className="bots-timeline__body">
                <b className="bots-timeline__title">{l.tag} {l.text}</b>
                {l.note ? <span className="bots-timeline__note">{prose(l.note)}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
