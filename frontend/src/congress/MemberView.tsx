/**
 * A member's page (ADR 066): who they are (portrait, seat, committees), what they reported this year, a year of their
 * trades week by week, every trade the reports hold (the filer's own words, the filing one click away) and every
 * report -- a scanned one listed as not read. Star to follow.
 */
import { useCongressMember } from './api';
import { PARTY_COLOR } from './constants';
import { Face, PartyBadge } from './Face';
import { chamberWord, day, lagClass, seat } from './format';
import { WeekBars } from './MostActive';
import { TradeTable } from './TradeTable';

export function MemberView({ bioguide, year, following, onToggleFollow, onBack, onTicker, onOpenTrader }: {
  bioguide: string;
  year: number;
  following: boolean;
  onToggleFollow: () => void;
  onBack: () => void;
  onTicker: (ticker: string) => void;
  onOpenTrader: (symbol: string) => void;
}) {
  const { data, error, missing } = useCongressMember(bioguide);
  const back = <button type="button" className="cg-back" onClick={onBack} data-testid="congress-back">‹ Congress</button>;
  if (missing) return <div className="cg-view">{back}<p className="cg-muted">No member {bioguide} is known on this desk.</p></div>;
  if (!data) return <div className="cg-view">{back}<p className="cg-muted" role="status">{error ?? 'Reading the member …'}</p></div>;
  const m = data.member;
  const kpis: [string, string, string?][] = [
    ['Trades this year', m.ytd.trades.toLocaleString()],
    ['Bought', m.ytd.buys.toLocaleString(), 'is-up'],
    ['Sold', m.ytd.sells.toLocaleString(), 'is-down'],
    ['Typical delay', m.median_lag_days != null ? `${Math.round(m.median_lag_days)} days` : '–', lagClass(m.median_lag_days)],
    ['Reported late', m.late.toLocaleString(), m.late ? 'is-late' : ''],
    ['Reports this year', `${m.ytd.reports}${m.ytd.paper ? ` (${m.ytd.paper} paper)` : ''}`],
  ];
  return (
    <div className="cg-view" data-testid="congress-member">
      {back}
      <section className="cg-card cg-member">
        <div className="cg-member__head">
          <Face member={m} size={96} ring={PARTY_COLOR[m.party ?? '']} />
          <div className="cg-member__who">
            <h2>{m.name} <PartyBadge party={m.party} size={22} /></h2>
            <div className="cg-muted">
              {m.chamber === 'senate' ? 'Senator' : 'Representative'} · {seat(m)} · {chamberWord(m.chamber)}
              {m.left ? <span className="cg-left"> · left Congress {day(m.left, year)}</span> : null}
            </div>
            {m.committees.length ? (
              <div className="cg-chips">{m.committees.map((c) => <span key={c} className="cg-chip">{c}</span>)}</div>
            ) : <div className="cg-muted cg-small">No committee seats on file</div>}
          </div>
          <button type="button" className={`cg-follow${following ? ' is-on' : ''}`} onClick={onToggleFollow}
            aria-pressed={following} data-testid="congress-follow">
            {following ? '★ Following' : '☆ Follow'}
          </button>
        </div>
        <div className="cg-kpis">
          {kpis.map(([label, value, cls]) => (
            <div key={label} className="cg-kpi"><span>{label}</span><b className={cls ?? ''}>{value}</b></div>
          ))}
        </div>
        <div className="cg-member__weeks">
          <span className="cg-muted cg-small">Trades by week since {day(data.weeks.from, year)} · bought up, sold down</span>
          <WeekBars weeks={data.weeks} width={900} height={64} stretch />
        </div>
      </section>
      <section className="cg-card">
        <div className="cg-card__head"><h3 className="cg-card__title">Every trade</h3>
          <span className="cg-card__source">{data.trades.length} in the reports Nova read · newest report first</span></div>
        <TradeTable trades={data.trades} year={year} onTicker={onTicker} onOpenTrader={onOpenTrader} />
      </section>
      <section className="cg-card">
        <div className="cg-card__head"><h3 className="cg-card__title">Reports</h3></div>
        <ul className="cg-reports">
          {data.reports.map((r) => (
            <li key={r.id}>
              <span className="cg-nowrap">{day(r.filed, year)}</span>
              <span>{r.kind === 'paper' ? 'Scanned paper report · not read' : r.read ? `${r.trades} trades` : r.error ?? 'Waiting to be read'}</span>
              {r.amends ? <span className="cg-muted">corrects the {day(r.amends, year)} report</span> : null}
              {r.amended_by ? <span className="cg-muted">replaced by a later amendment</span> : null}
              <a className="cg-link" href={r.url} target="_blank" rel="noreferrer">Filing ↗</a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
