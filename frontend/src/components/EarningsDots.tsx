/** Three-dot earnings window: tomorrow / today / yesterday. */
import {
  EARNINGS_DOT_EMPTY_TITLE,
  EARNINGS_DOT_ESTIMATED,
  EARNINGS_DOT_SESSION_AMC,
  EARNINGS_DOT_SESSION_BMO,
  EARNINGS_DOT_SESSION_INTRADAY,
} from '../constants';

export type EarningsSession = 'bmo' | 'amc' | 'intraday';

function sessionLabel(session: string | null | undefined): string | null {
  if (session === 'bmo') return EARNINGS_DOT_SESSION_BMO;
  if (session === 'amc') return EARNINGS_DOT_SESSION_AMC;
  if (session === 'intraday') return EARNINGS_DOT_SESSION_INTRADAY;
  return null;
}

export function earningsDotsTitle(
  date: string | null | undefined,
  session: string | null | undefined,
  estimated?: boolean | null,
): string {
  if (!date) return EARNINGS_DOT_EMPTY_TITLE;
  const parts: string[] = [];
  const sess = sessionLabel(session);
  if (sess) parts.push(sess);
  if (estimated) parts.push(EARNINGS_DOT_ESTIMATED);
  return parts.length ? `Earnings ${date} (${parts.join(', ')})` : `Earnings ${date}`;
}

export function EarningsDots({
  offset,
  earningsDate,
  session,
  estimated = false,
}: {
  offset: number | null | undefined;
  earningsDate?: string | null;
  session?: EarningsSession | string | null;
  estimated?: boolean | null;
}) {
  return (
    <span
      className="earnings-dots"
      title={earningsDotsTitle(earningsDate, session, estimated)}
    >
      <span className={`earnings-dot${offset === 1 ? ' lit' : ''}`} />
      <span className={`earnings-dot${offset === 0 ? ' lit' : ''}`} />
      <span className={`earnings-dot${offset === -1 ? ' lit' : ''}`} />
    </span>
  );
}
