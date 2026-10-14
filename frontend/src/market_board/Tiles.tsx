/**
 * The futures and macro tiles (ADR 053): every price IBKR's, each line from 04:00 ET to the later of the close and
 * its last point (futures and Bitcoin trade after 16:00; ADR 053 amendment 2026-10-13 evening). A price from a bar
 * the market has not traded past -- CME's 17:00-18:00 ET pause, a weekend -- is dimmed and says when it traded.
 * Each tile shows what it is as a picture and names its line's hours under it, as a quote page's 1-day chart does
 * (operator ask 2026-10-14: "it doesn't even tell you what it is. Is it the last 24 hours?").
 */
import { setNavPage } from '../workspace';
import { etTime, etWhen, price, signedNum, signedPct, signedPts, tone } from './format';
import { Spark } from './parts';
import { TileIcon } from './TileIcon';
import type { QuoteTile, Session } from './types';

function code(t: QuoteTile): string {
  return t.contract ?? t.symbol;
}

/** The line's time axis: 04:00 ET to the close, or on to its last point when it trades later. */
export function lineSpan(t: QuoteTile, session: Session): { from: number; to: number } {
  const from = session.open_at - 5.5 * 3600;   // 04:00 ET
  const lastT = t.line.length ? t.line[t.line.length - 1][0] : 0;
  return { from, to: Math.max(session.close_at, lastT) };
}

/** The line's hours under it: 04:00 at the left, the 09:30 open under its tick, the axis end at the right. */
function Axis({ from, to, open }: { from: number; to: number; open: number }) {
  const span = to - from || 1;
  const openAt = ((open - from) / span) * 100;
  return (
    <div className="mk-tile__axis" aria-hidden="true">
      <span style={{ left: 0 }}>{etTime(from)}</span>
      {open > from && open < to ? <span className="is-mid" style={{ left: `${openAt}%` }}>{etTime(open)}</span> : null}
      <span className="is-end">{etTime(to)}</span>
    </div>
  );
}

function Tile({ t, session, now }: { t: QuoteTile; session: Session; now: number }) {
  const { from, to } = lineSpan(t, session);
  const isSpread = t.kind === 'spread';
  const delayed = t.data_type === 'delayed' || t.data_type === 'delayed_frozen';
  const fromBars = t.data_type === 'bars';
  const stale = Boolean(t.stale) && t.at != null;
  const title = [t.error, t.price_basis === 'mid' ? 'No trade in the snapshot: the quoted midpoint' : null,
    stale ? `Not trading now: the last 5-minute bar's close, ${etWhen(t.at as number, now)} ET`
      : fromBars ? 'No live trade: the last 5-minute bar’s close, not a live quote' : null,
    `${t.exchange || 'computed'} via IBKR`].filter(Boolean).join(' · ');
  return (
    <div className={`mk-tile${t.error && t.last == null && !isSpread ? ' is-error' : ''}${stale ? ' is-stale' : ''}`}
      title={title} data-testid={`market-tile-${t.id}`}>
      <div className="mk-tile__name">
        <span>{t.label}</span>
        {t.id === 'btc' ? (
          <button type="button" className="mk-link" onClick={() => setNavPage('cryptos')}>Cryptos &rarr;</button>
        ) : (
          <span>
            {code(t)}
            {delayed ? <em className="mk-delayed"> delayed</em> : null}
            {stale && !isSpread ? <em className="mk-asof"> as of {etWhen(t.at as number, now)}</em>
              : fromBars ? <em className="mk-delayed"> bars {etTime(t.at)}</em> : null}
          </span>
        )}
      </div>
      <TileIcon id={t.id} />
      <div className="mk-tile__px">{isSpread ? signedPts(t.change_pct) : price(t.last)}</div>
      <div className={`mk-tile__chg is-${tone(t.change_pct)}`}>
        {isSpread
          ? t.change_pct == null ? '--' : t.change_pct >= 0 ? 'small caps leading' : 'small caps lagging'
          : t.id === 'tnx' && t.change_pct === 0 && t.last != null
            ? 'unchanged'
            : <>{signedNum(t.change, Math.abs(t.change ?? 0) >= 100 ? 0 : 2)}&nbsp; {signedPct(t.change_pct)}</>}
      </div>
      {t.error && t.last == null && !isSpread ? (
        <p className="mk-tile__error">{t.error}</p>
      ) : (
        <>
          <Spark points={t.line} height={36} from={from} to={to} zero={isSpread ? 0 : t.prev_close}
            mark={session.open_at} label={`${t.label}, today from ${etTime(from)} to ${etTime(to)} ET`} />
          {t.line.length >= 2 ? <Axis from={from} to={to} open={session.open_at} /> : null}
        </>
      )}
    </div>
  );
}

export function QuoteTiles({ quotes, session, now }: { quotes: QuoteTile[]; session: Session; now: number }) {
  return (
    <section className="mk-tiles" data-testid="market-tiles">
      <header className="mk-card__head mk-tiles__head">
        <h3>Futures &amp; macro</h3>
        <span className="mk-hint">
          <b>Today</b>, 5-minute line from 04:00 ET · change and dotted line = against the prior close · IBKR
        </span>
      </header>
      {quotes.map((t) => <Tile key={t.id} t={t} session={session} now={now} />)}
    </section>
  );
}
