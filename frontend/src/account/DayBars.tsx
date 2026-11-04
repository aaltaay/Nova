/**
 * P&L by day (ADR 069, mockup v1 item 4): your bar and the bots' bar for every day in the range, and the dashed
 * line of both added up -- what the calendar shows. A view of one book draws that book's bars alone. Days come
 * from the history's own `daily` rows; nothing is drawn for a day with no fill.
 */
import { OWNER_BOOK_BOTS, OWNER_BOOK_YOU, OWNER_DAY_EMPTY, OWNER_DAY_LEGEND_ALL } from '../constantGroups/owners';
import { formatSignedMoney } from '../components/globalBarMoney';
import type { HistoryDaily } from './accountHistoryTypes';
import type { OwnerView } from './ownerView';

interface Props {
  /** The range's days (the view's own, for one book). */
  daily: HistoryDaily[];
  view: OwnerView;
}

interface Day {
  date: string;
  you: number;
  bots: number;
  all: number;
}

const W = 900;
const H = 160;
const TOP = 10;
const BOTTOM = 22;
const LEFT = 52;

function days(daily: HistoryDaily[], view: OwnerView): Day[] {
  const byDate = new Map<string, Day>();
  for (const row of daily) {
    const day = byDate.get(row.date) ?? { date: row.date, you: 0, bots: 0, all: 0 };
    if (view.book === 'all') {
      day.you += row.you?.realized ?? 0;
      day.bots += row.bots?.realized ?? 0;
    } else if (view.book === 'you') day.you += row.realized;
    else day.bots += row.realized;
    day.all += row.realized;
    byDate.set(row.date, day);
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function DayBars({ daily, view }: Props) {
  const list = days(daily, view);
  if (!list.length) return <div className="acct-absent acct-absent--curve" data-testid="account-day-bars-empty">{OWNER_DAY_EMPTY}</div>;
  const values = list.flatMap((d) => [d.you, d.bots, d.all, 0]);
  const max = Math.max(...values) * 1.1 || 1;
  const min = Math.min(...values) * 1.1;
  const span = max - min || 1;
  const y = (v: number) => TOP + ((max - v) / span) * (H - TOP - BOTTOM);
  const step = (W - LEFT) / list.length;
  const bw = Math.max(2, Math.min(14, step * 0.32));
  const both = view.book === 'all';
  const label = (date: string) => `${Number(date.slice(5, 7))}/${Number(date.slice(8, 10))}`;
  const every = Math.max(1, Math.ceil(list.length / 14));
  const line = list.map((d, i) => `${LEFT + step * i + step / 2},${y(d.all)}`).join(' ');
  const bar = (v: number, x: number, cls: string, title: string) => {
    if (!v) return null;
    const y0 = y(0);
    const y1 = y(v);
    return <rect className={cls} x={x} y={Math.min(y0, y1)} width={bw} height={Math.max(1, Math.abs(y1 - y0))} rx={2}><title>{title}</title></rect>;
  };
  return (
    <div data-testid="account-day-bars">
      <svg className="acct-daybars" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="P&L by day">
        <line className="acct-daybars__zero" x1={LEFT} x2={W} y1={y(0)} y2={y(0)} />
        <text className="acct-daybars__tick" x={LEFT - 6} y={y(max / 1.1) + 4} textAnchor="end">{formatSignedMoney(max / 1.1, 0)}</text>
        {min < 0 && <text className="acct-daybars__tick" x={LEFT - 6} y={y(min / 1.1) + 4} textAnchor="end">{formatSignedMoney(min / 1.1, 0)}</text>}
        {list.map((d, i) => {
          const cx = LEFT + step * i + step / 2;
          return (
            <g key={d.date} data-testid={`account-day-bar-${d.date}`}>
              {both
                ? <>{bar(d.you, cx - bw - 1, 'is-you', `${d.date} ${OWNER_BOOK_YOU} ${formatSignedMoney(d.you)}`)}
                    {bar(d.bots, cx + 1, 'is-bots', `${d.date} ${OWNER_BOOK_BOTS} ${formatSignedMoney(d.bots)}`)}</>
                : bar(view.book === 'you' ? d.you : d.bots, cx - bw / 2, view.book === 'you' ? 'is-you' : 'is-bots',
                      `${d.date} ${formatSignedMoney(d.all)}`)}
              {i % every === 0 && <text className="acct-daybars__tick" x={cx} y={H - 6} textAnchor="middle">{label(d.date)}</text>}
            </g>
          );
        })}
        {both && <polyline className="acct-daybars__all" points={line} />}
      </svg>
      <div className="acct-clegend">
        {view.book !== 'bots' && <span><i className="acct-owner__dot is-you" />{OWNER_BOOK_YOU}</span>}
        {view.book !== 'you' && <span><i className="acct-owner__dot is-bots" />{OWNER_BOOK_BOTS}</span>}
        {both && <span><i className="acct-daybars__key" />{OWNER_DAY_LEGEND_ALL}</span>}
      </div>
    </div>
  );
}
