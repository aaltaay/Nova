/** The Activity column: every entry, add and exit of the day, newest first, with the screenshot behind it. */
import { activity, type ActivityVerb } from './activity';
import { FT_ACTIVITY, FT_NEWEST_FIRST, FT_NO_ACTIVITY } from './constants';
import { FeedImage } from './FeedImage';
import { etTime, price } from './format';
import { SideChip } from './parts';
import type { FollowedTrader } from './types';

const VERB_CLASS: Record<ActivityVerb, string> = {
  opened: 'ft-verb--open',
  holding: 'ft-verb--hold',
  'added to': 'ft-verb--add',
  closed: 'ft-verb--close',
};

export function ActivityFeed({ traders, onProof }: { traders: FollowedTrader[]; onProof: (id: string) => void }) {
  const items = activity(traders);
  return (
    <aside className="ft-card ft-activity" aria-labelledby="ft-activity" data-testid="ft-activity">
      <div className="ft-activity__head">
        <h2 id="ft-activity" className="ft-eyebrow">{FT_ACTIVITY}</h2>
        <span className="ft-muted ft-small">{FT_NEWEST_FIRST}</span>
      </div>
      {items.length === 0 && <div className="ft-activity__item ft-muted">{FT_NO_ACTIVITY}</div>}
      {items.map((e) => (
        <div key={e.key} className="ft-activity__item" data-testid={`ft-activity-${e.key}`}>
          <div className="ft-activity__line">
            <span className="ft-mono ft-muted ft-activity__time">{etTime(e.ts)}</span>
            <button type="button" className={`ft-link ft-verb ${VERB_CLASS[e.verb]}`} onClick={() => onProof(e.tradeId)}>
              {e.trader} {e.verb}
            </button>
            <SideChip side={e.side} />
            <span className="ft-ticker">{e.symbol}</span>
            {e.price !== null && <span className="ft-mono">{price(e.price)}</span>}
          </div>
          {e.note && <span className="ft-small ft-muted ft-activity__note">{e.note}</span>}
          {e.image && <FeedImage path={e.image} className="ft-activity__img" alt={`${e.trader}'s position bar at ${etTime(e.ts)}`} />}
        </div>
      ))}
    </aside>
  );
}
