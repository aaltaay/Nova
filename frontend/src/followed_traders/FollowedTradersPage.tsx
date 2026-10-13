/**
 * The Followed traders page -- a placeholder. The operator is approving the page's design (2026-10-13); until then
 * this proves the data flows: every state said (not configured, the feed down or unreadable, its own problem, the
 * capture stale, how open positions are priced) and each trade as one line of text, never an empty list. The rail
 * shows it only when the backend has a feed configured (enabledStore). Schema: architecture/schema/followed-traders.md.
 */
import {
  FOLLOWED_CAPTURE_STALE_SEC,
  FT_BAD_ANSWER,
  FT_LOADING,
  FT_NO_STATUS,
  FT_NO_TRADES,
  FT_OFF,
  FT_PLACEHOLDER_NOTE,
  FT_READ_FAILED,
  FT_TITLE,
  FT_UNREACHABLE,
} from './constants';
import { duration, entered, etTime, exitPrice, exited, held, plPct, plPerShare, price } from './format';
import type { FollowedCapture, FollowedRecord, FollowedTrade } from './types';
import { useFollowedDay } from './useFollowedDay';

interface Props {
  onOpenTrader?: (symbol: string) => void;
}

export function FollowedTradersPage(_props: Props) {
  const { data, error, off } = useFollowedDay(null);
  let body;
  if (off) body = <p data-testid="ft-state">{FT_OFF}</p>;
  else if (!data) body = <p data-testid="ft-state">{error ? `${FT_READ_FAILED} ${error}` : FT_LOADING}</p>;
  else if (data.feed.state !== 'ok') {
    body = (
      <p data-testid="ft-state">
        {data.feed.state === 'unreachable' ? FT_UNREACHABLE : FT_BAD_ANSWER} {data.feed.error}
      </p>
    );
  } else {
    body = (
      <>
        <p data-testid="ft-capture">{captureLine(data.capture)}</p>
        <p data-testid="ft-prices">
          Prices: {data.prices?.state}
          {data.prices?.why ? ` (${data.prices.why})` : ''}
          {data.overall ? ` · everyone: ${recordLine(data.overall)}` : ''}
          {error ? ` · last read failed: ${error}` : ''}
        </p>
        {data.traders.length === 0 && <p data-testid="ft-state">{FT_NO_TRADES}</p>}
        {data.traders.map((t) => (
          <section key={t.name} data-testid={`ft-trader-${t.name}`} className="mt-3">
            <h3 className="font-semibold">
              {t.name} · {recordLine(t.record)}
            </h3>
            <ul>
              {[...t.open, ...t.closed].map((trade) => (
                <li key={trade.id} data-testid={`ft-row-${trade.id}`}>
                  {tradeLine(trade)}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </>
    );
  }
  return (
    <div className="flex-1 min-h-0 overflow-auto p-4 text-sm" data-testid="followed-traders-page">
      <h2 className="text-base font-bold">{FT_TITLE}</h2>
      <p className="opacity-70">{FT_PLACEHOLDER_NOTE}</p>
      {body}
    </div>
  );
}

export function captureLine(c: FollowedCapture | null): string {
  if (!c) return FT_NO_STATUS;
  const stale = c.age_sec !== null && c.age_sec > FOLLOWED_CAPTURE_STALE_SEC;
  if (stale || (c.updated_at === null && c.problem)) {
    const why = c.problem ? `: ${c.problem}` : '';
    return c.age_sec !== null ? `Capture stopped ${duration(c.age_sec)} ago${why}` : `Capture stopped${why}`;
  }
  const parts = [c.live ? 'Live' : 'Not live'];
  if (c.age_sec !== null) parts.push(`read ${duration(c.age_sec)} ago`);
  if (c.clock) parts.push(`${c.clock} ET`);
  if (!c.bar_visible) parts.push('positions hidden on the feed right now');
  return parts.join(' · ');
}

export function recordLine(r: FollowedRecord): string {
  const rate = r.win_rate === null ? 'win rate —' : `win rate ${r.win_rate}%`;
  return `${r.wins}W / ${r.losses}L / ${r.open} open (${r.scratches} scratch, ${r.unscored} unscored) · ${rate}`;
}

export function tradeLine(t: FollowedTrade): string {
  const parts = [`${t.side.toUpperCase()} ${t.symbol}`, `in ${entered(t.entry)}`, `entry ${price(t.entry.avg_price)}`];
  if (t.entry.first_price !== t.entry.avg_price) parts.push(`first ${price(t.entry.first_price)}`);
  if (t.status === 'open') {
    parts.push(t.now?.state === 'live' ? `now ${price(t.now.price)}` : `now: ${t.now?.state ?? '—'}`);
  } else if (t.exit) {
    const when = t.status === 'unknown' ? 'close not seen' : exited(t.exit);
    parts.push(`exit ${exitPrice(t.exit)} (${when}${t.exit.state === 'range' ? ', estimated' : ''})`);
    if (t.exit.trade_ts) parts.push(`IBKR print ${etTime(t.exit.trade_ts)}`);
  }
  parts.push(`P/L ${plPerShare(t.pl, t.entry.avg_price)} / sh (${plPct(t.pl)})`);
  if (t.result) parts.push(t.result);
  parts.push(`held ${held(t.held)}`);
  return parts.join(' · ');
}
