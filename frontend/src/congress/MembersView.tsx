/**
 * Members and Following (ADR 066): every member -- and every filer who left -- with what they reported this year,
 * busiest first; search by name or state; a star to follow. Following is the same list, the members starred.
 */
import { useMemo, useState } from 'react';
import { useCongressMembers } from './api';
import { Face, PartyBadge } from './Face';
import { chamberWord, day, lagClass, seat } from './format';
import type { Chamber, MemberStats } from './types';

type Sort = 'trades' | 'name' | 'delay' | 'last';

export function MembersView({ year, chamber, query, only, following, onToggleFollow, onOpen }: {
  year: number;
  chamber: Chamber | null;
  query: string;
  only: string[] | null;
  following: string[];
  onToggleFollow: (bioguide: string) => void;
  onOpen: (bioguide: string) => void;
}) {
  const { data, error } = useCongressMembers();
  const [sort, setSort] = useState<Sort>('trades');
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (data?.members ?? []).filter((m) =>
      (!chamber || m.chamber === chamber) && (!only || only.includes(m.bioguide))
      && (!q || m.name.toLowerCase().includes(q) || (m.state ?? '').toLowerCase() === q || seat(m).toLowerCase().includes(q)));
    const by: Record<Sort, (a: MemberStats, b: MemberStats) => number> = {
      trades: (a, b) => b.ytd.trades - a.ytd.trades || a.name.localeCompare(b.name),
      name: (a, b) => a.name.localeCompare(b.name),
      delay: (a, b) => (b.median_lag_days ?? -1) - (a.median_lag_days ?? -1),
      last: (a, b) => (b.last_filed ?? '').localeCompare(a.last_filed ?? ''),
    };
    return list.sort(by[sort]);
  }, [data, chamber, query, only, sort]);
  if (!data) return <p className="cg-muted cg-empty" role="status">{error ?? 'Reading the members …'}</p>;
  if (only && !only.length) {
    return <p className="cg-muted cg-empty" data-testid="congress-following-empty">Star a member on their page or here to follow them.</p>;
  }
  const head = (id: Sort, label: string, cls = '') => (
    <th className={cls}><button type="button" className={`cg-sort${sort === id ? ' is-on' : ''}`} onClick={() => setSort(id)}>{label}</button></th>
  );
  return (
    <section className="cg-card cg-members" data-testid={only ? 'congress-following' : 'congress-members'}>
      <div className="cg-tablewrap">
        <table className="cg-table">
          <thead>
            <tr>
              <th />{head('name', 'Member')}<th>Seat</th>{head('trades', 'Trades this year', 'r')}<th>Bought / sold</th>
              {head('last', 'Last report')}{head('delay', 'Typical delay', 'r')}<th className="r">Late</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => {
              const total = Math.max(1, m.ytd.buys + m.ytd.sells);
              const on = following.includes(m.bioguide);
              return (
                <tr key={m.bioguide} className="is-clickable" onClick={() => onOpen(m.bioguide)} data-testid={`congress-member-${m.bioguide}`}>
                  <td>
                    <button type="button" className={`cg-star${on ? ' is-on' : ''}`} aria-pressed={on}
                      aria-label={on ? `Stop following ${m.name}` : `Follow ${m.name}`}
                      onClick={(e) => { e.stopPropagation(); onToggleFollow(m.bioguide); }}>{on ? '★' : '☆'}</button>
                  </td>
                  <td><span className="cg-who"><Face member={m} size={28} /><span>{m.name}</span><PartyBadge party={m.party} size={16} /></span></td>
                  <td className="cg-nowrap">{seat(m)} · {chamberWord(m.chamber)}{m.left ? <span className="cg-left"> · left {day(m.left, year)}</span> : null}</td>
                  <td className="r"><b>{m.ytd.trades.toLocaleString()}</b>{m.ytd.paper ? <span className="cg-muted cg-small"> +{m.ytd.paper} paper</span> : null}</td>
                  <td>
                    {m.ytd.trades ? (
                      <span className="cg-split" title={`${m.ytd.buys} bought · ${m.ytd.sells} sold`}>
                        <i className="is-buy" style={{ width: `${(100 * m.ytd.buys) / total}%` }} />
                        <i className="is-sell" style={{ width: `${(100 * m.ytd.sells) / total}%` }} />
                      </span>
                    ) : <span className="cg-muted">–</span>}
                  </td>
                  <td className="cg-nowrap">{m.last_filed ? day(m.last_filed, year) : <span className="cg-muted">none kept</span>}</td>
                  <td className={`r ${lagClass(m.median_lag_days)}`}>{m.median_lag_days != null ? `${Math.round(m.median_lag_days)} d` : '–'}</td>
                  <td className={`r ${m.late ? 'is-late' : ''}`}>{m.late || ''}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
