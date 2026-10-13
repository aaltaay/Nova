/**
 * "On their bar right now": each trader's slot as the feed last saw it beside what the vision confirmed there. The
 * slot image is asked again with each capture update. A feed that sends no slot image gets the trader's newest
 * evidence image in its place, labelled with when it was taken, never passed off as now.
 */
import { captureStopped } from './capture';
import {
  FT_BAR_CONFIRMED,
  FT_BAR_LAST_READ,
  FT_BAR_LAST_SEEN,
  FT_BAR_NO_IMAGE,
  FT_BAR_NONE,
  FT_BAR_NOW,
  FT_BAR_NOW_SUB,
  FT_BAR_STAND_IN,
  FT_NO_POSITIONS,
} from './constants';
import { FeedImage } from './FeedImage';
import { etTime, price } from './format';
import { sideRow } from './proof';
import type { BarPosition, FollowedCapture, FollowedTrader } from './types';

interface StandIn {
  path: string;
  ts: number;
}

/** The trader's newest evidence image of the day, and when it was taken. */
export function newestEvidence(trader: FollowedTrader | undefined): StandIn | null {
  if (!trader) return null;
  let best: StandIn | null = null;
  for (const t of [...trader.open, ...trader.closed]) {
    const shots: [string | null, number | null][] = [[t.evidence.entry, t.entry.ts], [t.evidence.exit, t.exit?.to_ts ?? null]];
    for (const [path, ts] of shots) {
      if (path && ts !== null && (!best || ts > best.ts)) best = { path, ts };
    }
  }
  return best;
}

function Chips({ positions, side }: { positions: BarPosition[]; side: BarPosition['side'] }) {
  const row = sideRow(positions, side);
  if (row.length === 0) return <span className="ft-read-chip ft-read-chip--none">{side.toUpperCase()} none</span>;
  return (
    <>
      {row.map((p) => (
        <span key={`${p.side}:${p.symbol}`} className={`ft-read-chip ft-read-chip--${side}`}>
          {side.toUpperCase()} {p.symbol} {price(p.price)}
        </span>
      ))}
    </>
  );
}

interface Props {
  capture: FollowedCapture;
  traders: FollowedTrader[];
}

export function BarNow({ capture, traders }: Props) {
  const bar = capture.bar;
  const sub = captureStopped(capture) || !capture.live ? FT_BAR_LAST_READ : !capture.bar_visible ? FT_BAR_LAST_SEEN
    : FT_BAR_NOW_SUB;
  return (
    <section className="ft-section" aria-labelledby="ft-bar-now" data-testid="ft-bar-now">
      <div className="ft-section__head">
        <h2 id="ft-bar-now" className="ft-eyebrow">{FT_BAR_NOW}</h2>
        <span className={`ft-small ${sub === FT_BAR_NOW_SUB ? 'ft-muted' : 'ft-warn-text'}`} data-testid="ft-bar-now-sub">{sub}</span>
      </div>
      {bar === null ? <div className="ft-empty">{FT_BAR_NONE}</div> : (
        <div className="ft-bar-grid">
          {bar.map((slot) => {
            const standIn = slot.image ? null : newestEvidence(traders.find((t) => t.name === slot.trader));
            return (
              <div key={slot.trader} className="ft-card ft-slot" data-testid={`ft-slot-${slot.trader}`}>
                {slot.image ? (
                  <FeedImage path={slot.image} version={capture.updated_at} className="ft-slot__img"
                    alt={`${slot.trader}'s slot on the stream's position bar`} />
                ) : standIn ? (
                  <figure className="ft-slot__fig">
                    <FeedImage path={standIn.path} className="ft-slot__img" alt={`${slot.trader}'s slot at ${etTime(standIn.ts)}`} />
                    <figcaption className="ft-muted ft-small">{FT_BAR_STAND_IN} · {etTime(standIn.ts)} ET</figcaption>
                  </figure>
                ) : <span className="ft-img-missing ft-slot__img">{FT_BAR_NO_IMAGE}</span>}
                <div className="ft-slot__read">
                  <span className="ft-muted ft-small">Read as</span>
                  <span className="ft-slot__name">{slot.trader}</span>
                  {slot.positions.length === 0
                    ? <span className="ft-read-chip ft-read-chip--none">{FT_NO_POSITIONS}</span>
                    : <><Chips positions={slot.positions} side="long" /><Chips positions={slot.positions} side="short" /></>}
                  <span className="ft-slot__confirmed ft-muted ft-small">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>
                    {FT_BAR_CONFIRMED}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
