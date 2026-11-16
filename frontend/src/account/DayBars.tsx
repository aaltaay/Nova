/**
 * P&L by day (ADR 072, mockup three-books v1 item 4): for every day in the range a bar per book that traded --
 * You, Claude, The brain, Earlier bots, side by side in that order -- and the dashed line of all of them added up,
 * what the calendar shows. The legend above names each book with its total over the range. A view of one book
 * draws that book's bars alone. Days come from the history's own `daily` rows; nothing is drawn for a day with no
 * fill.
 */
import { OWNER_DAY_EMPTY, OWNER_NAMES, OWNER_SWITCH_LABELS, OWNERS, ownerBotName, type Owner } from '../constantGroups/owners';
import { formatSignedMoney } from '../components/globalBarMoney';
import { toneClass, toneOf } from './accountBits';
import type { HistoryDaily } from './accountHistoryTypes';
import { emptySplit, type DaySplit, type OwnerView } from './ownerView';

interface Props {
  /** The range's days (the view's own, for one book). */
  daily: HistoryDaily[];
  view: OwnerView;
}

interface Day {
  date: string;
  books: DaySplit;
  all: number;
}

const W = 900;
const H = 160;
const TOP = 10;
const BOTTOM = 22;
const LEFT = 52;
const GAP = 2;
const CENT = 0.005;

function days(daily: HistoryDaily[], view: OwnerView): Day[] {
  const byDate = new Map<string, Day>();
  for (const row of daily) {
    const day = byDate.get(row.date) ?? { date: row.date, books: emptySplit(), all: 0 };
    if (view.book === 'all') for (const o of OWNERS) day.books[o] += row[o]?.realized ?? 0;
    else day.books[view.book] += row.realized;
    day.all += row.realized;
    byDate.set(row.date, day);
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function DayBars({ daily, view }: Props) {
  const list = days(daily, view);
  const series: readonly Owner[] = view.book === 'all' ? OWNERS : [view.book];
  const both = view.book === 'all';
  if (!list.length) return <div className="acct-absent acct-absent--curve" data-testid="account-day-bars-empty">{OWNER_DAY_EMPTY}</div>;
  const totals = emptySplit();
  for (const d of list) for (const o of series) totals[o] += d.books[o];
  const allTotal = list.reduce((s, d) => s + d.all, 0);
  const values = list.flatMap((d) => [...series.map((o) => d.books[o]), d.all, 0]);
  const max = Math.max(...values) * 1.1 || 1;
  const min = Math.min(...values) * 1.1;
  const span = max - min || 1;
  const y = (v: number) => TOP + ((max - v) / span) * (H - TOP - BOTTOM);
  const step = (W - LEFT) / list.length;
  const bw = Math.max(2, Math.min(10, (step * 0.7 - GAP * (series.length - 1)) / series.length));
  const label = (date: string) => `${Number(date.slice(5, 7))}/${Number(date.slice(8, 10))}`;
  const every = Math.max(1, Math.ceil(list.length / 14));
  const centre = (i: number) => LEFT + step * i + step / 2;
  const line = list.map((d, i) => `${centre(i)},${y(d.all)}`).join(' ');
  const name = (o: Owner) => (o === 'earlier_bots' && view.bot ? ownerBotName(view.bot) : OWNER_NAMES[o]);
  return (
    <div data-testid="account-day-bars">
      <div className="acct-daylegend" data-testid="account-day-legend">
        {series.map((o) => (
          <span key={o} data-owner={o}>
            <i className={`acct-owner__dot is-${o}`} aria-hidden />{name(o)}
            <b className={`acct-num ${toneClass(toneOf(totals[o]))}`}>{formatSignedMoney(totals[o])}</b>
          </span>
        ))}
        {both && (
          <span data-owner="all">
            <i className="acct-daybars__key" aria-hidden />{OWNER_SWITCH_LABELS.all}
            <b className={`acct-num ${toneClass(toneOf(allTotal))}`}>{formatSignedMoney(allTotal)}</b>
          </span>
        )}
      </div>
      <svg className="acct-daybars" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="P&L by day">
        <line className="acct-daybars__zero" x1={LEFT} x2={W} y1={y(0)} y2={y(0)} />
        <text className="acct-daybars__tick" x={LEFT - 6} y={y(max / 1.1) + 4} textAnchor="end">{formatSignedMoney(max / 1.1, 0)}</text>
        {min < 0 && <text className="acct-daybars__tick" x={LEFT - 6} y={y(min / 1.1) + 4} textAnchor="end">{formatSignedMoney(min / 1.1, 0)}</text>}
        {list.map((d, i) => {
          const cx = centre(i);
          // Only the books that traded that day, centred on the day as a group.
          const traded = series.filter((o) => Math.abs(d.books[o]) >= CENT);
          const width = traded.length * bw + (traded.length - 1) * GAP;
          return (
            <g key={d.date} data-testid={`account-day-bar-${d.date}`}>
              {traded.map((o, k) => {
                const v = d.books[o];
                const y0 = y(0);
                const y1 = y(v);
                return (
                  <rect key={o} className={`is-${o}`} data-owner={o} x={cx - width / 2 + k * (bw + GAP)} y={Math.min(y0, y1)}
                    width={bw} height={Math.max(1, Math.abs(y1 - y0))} rx={1}>
                    <title>{`${d.date} ${OWNER_NAMES[o]} ${formatSignedMoney(v)}`}</title>
                  </rect>
                );
              })}
              {i % every === 0 && <text className="acct-daybars__tick" x={cx} y={H - 6} textAnchor="middle">{label(d.date)}</text>}
            </g>
          );
        })}
        {both && <polyline className="acct-daybars__all" points={line} />}
        {both && list.map((d, i) => <circle key={d.date} className="acct-daybars__dot" cx={centre(i)} cy={y(d.all)} r={2.4} />)}
      </svg>
    </div>
  );
}
