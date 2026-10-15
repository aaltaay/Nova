/**
 * "Check a read": one trade's entry and exit screenshots beside what the vision read off the slot at each, and every
 * read in between that differed from what was logged and was ignored. Nova only reads the feed: there is no button
 * that drops or confirms a trade.
 */
import { dayLabel } from './calendar';
import {
  FT_BACK,
  FT_CHECK_A_READ,
  FT_ENTRY,
  FT_EXIT,
  FT_IGNORED,
  FT_NEVER_EDITS,
  FT_NO_EVIDENCE,
  FT_NO_POSITIONS,
  FT_NOT_ON_BAR,
  FT_READS_LOADING,
  FT_READS_NONE,
  FT_READS_TITLE,
  FT_TICKER_CHECK,
  FT_WHAT_WAS_READ,
} from './constants';
import { FeedImage } from './FeedImage';
import { duration, entered, etTime, exitPrice, exited, held, plPct, plPerShare, price } from './format';
import { Face, SideChip, Ticker, TickerMark } from './parts';
import { exitTs, judgeReads, noExitImage, readAt, sideRow, type JudgedRead } from './proof';
import { tickerUnsettled } from './ticker';
import type { BarPosition, FollowedRead, FollowedTrade } from './types';
import { useFollowedReads } from './useFollowedFetch';

function Row({ positions, side, mark, kind }: { positions: BarPosition[]; side: BarPosition['side']; mark: string;
  kind: 'new' | 'gone' }) {
  const row = sideRow(positions, side);
  if (row.length === 0) return <span>{FT_NO_POSITIONS}</span>;
  return (
    <span className="ft-mono">
      {row.map((p, i) => (
        <span key={p.symbol}>
          {i > 0 && ' · '}
          <span className={p.symbol === mark ? `ft-mark ft-mark--${kind}` : undefined}>
            <Ticker symbol={p.symbol} className="" /> {price(p.price)}{p.symbol === mark ? ` ${kind}` : ''}
          </span>
        </span>
      ))}
    </span>
  );
}

function ReadGrid({ read, trade, kind, loggedAt }: { read: FollowedRead | null; trade: FollowedTrade;
  kind: 'new' | 'gone'; loggedAt: string }) {
  if (!read) return <span className="ft-muted ft-small">{FT_READS_LOADING}</span>;
  // At the exit the position is gone from the read; show it struck through on its row.
  const positions = kind === 'gone' && !read.positions.some((p) => p.symbol === trade.symbol)
    ? [...read.positions, { side: trade.side, symbol: trade.symbol, price: trade.entry.avg_price }]
    : read.positions;
  return (
    <div className="ft-read-grid">
      <span className="ft-muted">Name tag</span>
      <span className="ft-strong">{read.seen ? trade.trader : FT_NOT_ON_BAR}</span>
      <span className="ft-muted">LONG row</span><Row positions={positions} side="long" mark={trade.symbol} kind={kind} />
      <span className="ft-muted">SHORT row</span><Row positions={positions} side="short" mark={trade.symbol} kind={kind} />
      <span className="ft-muted">Logged</span><span>{loggedAt}</span>
    </div>
  );
}

function readText(r: FollowedRead): string {
  if (!r.seen) return FT_NOT_ON_BAR;
  if (r.unparsed.length) return `unreadable: ${r.unparsed.join(' | ')}`;
  if (r.positions.length === 0) return FT_NO_POSITIONS;
  return r.positions.map((p) => `${p.side.toUpperCase()} ${p.symbol} ${price(p.price)}`).join(' · ');
}

function ReadList({ reads }: { reads: JudgedRead[] }) {
  return (
    <div className="ft-table-scroll">
      <table className="ft-table ft-table--reads">
        <thead><tr><th>From</th><th>Kept</th><th>What was read</th><th /></tr></thead>
        <tbody>
          {reads.map((r) => (
            <tr key={r.ts} className={r.verdict === 'ignored' ? 'is-ignored' : undefined}>
              <td className="ft-mono">{etTime(r.ts)}</td>
              <td className="ft-mono ft-muted">{r.until_ts === null ? '—' : duration(r.until_ts - r.ts)}</td>
              <td className="ft-mono">{readText(r)}</td>
              <td>{r.verdict === 'ignored' ? <span className="ft-result ft-result--unscored">{FT_IGNORED}</span>
                : r.verdict === 'entry' || r.verdict === 'exit' ? <span className="ft-muted ft-small">{r.verdict}</span> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  trade: FollowedTrade;
  face: string | null;
  date: string;
  generatedAt: number;
  onBack: () => void;
}

export function ProofView({ trade, face, date, generatedAt, onBack }: Props) {
  const out = exitTs(trade);
  const from = trade.entry.since_ts ?? trade.entry.ts;
  const to = out ?? Math.max(from, Math.floor(generatedAt));
  const { data, error } = useFollowedReads(date, trade.trader, from, to);
  const judged = data?.available ? judgeReads(trade, data.reads) : null;
  const ignored = judged ? judged.reads.filter((r) => r.verdict === 'ignored') : [];
  const readsNote = error ? `The read log did not load: ${error}` : data && !data.available
    ? data.why ?? data.feed.error ?? '' : null;
  const facts = [`In ${entered(trade.entry)}`];
  if (trade.exit && trade.status === 'closed') {
    const priced = trade.exit.state === 'at' || trade.exit.state === 'range';
    facts.push(`out ${exited(trade.exit)}`, `exit ${exitPrice(trade.exit)}${priced ? ' (IBKR)' : ''}`);
  }
  facts.push(`held ${held(trade.held)}`);
  if (trade.pl) facts.push(`P/L ${plPerShare(trade.pl, trade.entry.avg_price)} (${plPct(trade.pl)})`);
  if (tickerUnsettled(trade)) facts.push(`${FT_TICKER_CHECK}: ${trade.ticker?.why ?? ''}`);
  return (
    <div className="ft-proof" data-testid="ft-proof">
      <div className="ft-proof__top">
        <button type="button" className="ft-link ft-back" onClick={onBack} data-testid="ft-proof-back">‹ {FT_BACK}</button>
        <span className="ft-muted ft-small">{FT_CHECK_A_READ} · {dayLabel(date)}</span>
      </div>
      <div className="ft-proof__who">
        <Face path={face} name={trade.trader} size="lg" />
        <div className="ft-stack">
          <div className="ft-proof__title">
            <span className="ft-strong">{trade.trader}</span><SideChip side={trade.side} />
            <Ticker symbol={trade.symbol} className="ft-strong" /><TickerMark ticker={trade.ticker} />
            <span className="ft-mono">{price(trade.entry.avg_price)}</span>
          </div>
          <span className="ft-muted">{facts.join(' · ')}</span>
        </div>
      </div>
      <div className="ft-proof__pair">
        <section className="ft-card ft-proof__card" aria-label={FT_ENTRY}>
          <div className="ft-proof__card-head"><h2 className="ft-eyebrow ft-eyebrow--long">{FT_ENTRY}</h2>
            <span className="ft-mono ft-muted ft-small">{entered(trade.entry)}</span></div>
          <FeedImage path={trade.evidence.entry} className="ft-proof__img" missing={FT_NO_EVIDENCE}
            alt={`${trade.trader}'s position bar at the entry`} />
          <span className="ft-eyebrow">{FT_WHAT_WAS_READ}</span>
          {readsNote !== null ? <span className="ft-muted ft-small">{readsNote}</span>
            : <ReadGrid read={data ? readAt(data.reads, trade.entry.ts) : null} trade={trade} kind="new"
              loggedAt={etTime(trade.entry.ts)} />}
        </section>
        <section className="ft-card ft-proof__card" aria-label={FT_EXIT}>
          <div className="ft-proof__card-head"><h2 className="ft-eyebrow ft-eyebrow--exit">{FT_EXIT}</h2>
            <span className="ft-mono ft-muted ft-small">{trade.exit && out !== null ? exited(trade.exit) : ''}</span></div>
          {out === null ? <div className="ft-empty">{noExitImage(trade)}</div> : (
            <>
              {/* Closed when they left the bar: an exit time, but no close was seen, so no picture of one. */}
              {trade.left_bar ? <div className="ft-empty">{noExitImage(trade)}</div>
                : <FeedImage path={trade.evidence.exit} className="ft-proof__img" missing={FT_NO_EVIDENCE}
                  alt={`${trade.trader}'s position bar at the exit`} />}
              <span className="ft-eyebrow">{FT_WHAT_WAS_READ}</span>
              {readsNote !== null ? <span className="ft-muted ft-small">{readsNote}</span>
                : <ReadGrid read={data ? readAt(data.reads, out) : null} trade={trade} kind="gone" loggedAt={etTime(out)} />}
            </>
          )}
        </section>
      </div>
      {judged && (
        <section className="ft-card ft-proof__reads" aria-label={FT_READS_TITLE}>
          <div className="ft-proof__ignored">
            {ignored.length === 0 ? FT_READS_NONE
              : `${ignored.length} read${ignored.length === 1 ? '' : 's'} during this trade differed from what was logged and ${ignored.length === 1 ? 'was' : 'were'} ignored: never the same on enough frames in a row.`}
          </div>
          <details>
            <summary>{FT_READS_TITLE} ({judged.reads.length}{data?.truncated ? ', the first ones' : ''})</summary>
            <ReadList reads={judged.reads} />
          </details>
        </section>
      )}
      <p className="ft-muted ft-small">{FT_NEVER_EDITS}</p>
    </div>
  );
}
