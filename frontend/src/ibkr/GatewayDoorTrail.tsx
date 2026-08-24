/**
 * Operator-visible Paper/Live door trail (IBC 2FA, attach/refuse).
 * Not the order Activity ledger.
 */
import {
  formatDoorTrailLine,
  formatDoorTrailTime,
  newestFirst,
} from './formatDoorTrail';
import { useGatewayDoorTrail } from './useGatewayDoorTrail';
import {
  DOOR_TRAIL_EMPTY,
  DOOR_TRAIL_HINT,
  DOOR_TRAIL_KICKER,
  DOOR_TRAIL_REFRESH,
  DOOR_TRAIL_TITLE,
} from './gatewayUxConstants';
import './gatewayDoorTrail.css';

export function GatewayDoorTrail({ compact = false }: { compact?: boolean }) {
  const { rows, loading, error, refresh } = useGatewayDoorTrail(true);
  const shown = newestFirst(rows);

  return (
    <section
      className={`door-trail${compact ? ' door-trail--compact' : ''}`}
      data-testid="gateway-door-trail"
      aria-label={DOOR_TRAIL_TITLE}
    >
      <header className="door-trail__head">
        <div>
          <p className="door-trail__kicker">{DOOR_TRAIL_KICKER}</p>
          <h3 className="door-trail__title">{DOOR_TRAIL_TITLE}</h3>
          {!compact && <p className="door-trail__hint">{DOOR_TRAIL_HINT}</p>}
        </div>
        <button type="button" className="ibkr-btn-secondary" onClick={refresh}>
          {DOOR_TRAIL_REFRESH}
        </button>
      </header>
      {error && (
        <p className="door-trail__error" data-testid="gateway-door-trail-error">
          {error}
        </p>
      )}
      {loading && shown.length === 0 && !error && (
        <p className="door-trail__empty">Loading trail...</p>
      )}
      {!loading && shown.length === 0 && !error && (
        <p className="door-trail__empty" data-testid="gateway-door-trail-empty">
          {DOOR_TRAIL_EMPTY}
        </p>
      )}
      {shown.length > 0 && (
        <ol className="door-trail__list">
          {shown.map((row, idx) => (
            <li key={`${row.ts ?? idx}-${row.event ?? idx}`} className="door-trail__row">
              <span className="door-trail__when">{formatDoorTrailTime(row.ts)}</span>
              <span className="door-trail__actor">{row.actor || 'nova'}</span>
              <span className="door-trail__line">{formatDoorTrailLine(row)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
