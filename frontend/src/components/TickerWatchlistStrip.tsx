/** The selected ticker's watchlist read in the side panel: the Five Pillars with their
 * reasons, where the setup scanners have it (its most advanced setup, ADR 031), and
 * the toggle that lets the bot trade it (ADR 042 F: a refusal is a notice).
 * Any symbol gets its pillars (operator ask, 2026-09-23): a ranked one from the
 * watchlist poll, any other graded by the backend from its board row or live quote.
 * On a Sim replay desk the grade is the replayed day's own board row at the playhead, named
 * with its moment and board, or the card says why there is none (operator report, 2026-10-12). */
import {
  TAPE_VERDICT_LABELS,
  TICKER_WATCHLIST_STRIP_EMPTY,
  TICKER_WATCHLIST_STRIP_TITLE,
  WATCHLIST_BOT_OFF_TITLE,
  WATCHLIST_BOT_ON_TITLE,
  WATCHLIST_PILLAR_NAMES,
} from '../constants';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import {
  fmtPx,
  rowsBySymbol,
  setupLabel,
  setupTypeOf,
  stateWords,
  tapeWords,
  useSetupsBoard,
  type SetupRow,
} from '../setups';
import { tipProps } from '../ux/hoverTip';
import {
  WATCHLIST_STRIP_GRADING,
  WATCHLIST_STRIP_SOURCES,
  replayPillarsAbsent,
  replayPillarsSource,
  watchlistStripRank,
} from '../constantGroups/watchlist_strip';
import type { WatchlistEntry } from '../strategy/types';
import { useSymbolPillars, type PillarsReplay } from '../strategy/useSymbolPillars';
import { newsCell } from '../strategy/watchlistFormat';
import { replayMomentLabel } from '../utils/replayMoment';

interface Props {
  /** The symbol's ranked watchlist entry, when the watchlist holds it. */
  entry: WatchlistEntry | null | undefined;
  /** The symbol on screen: graded on demand when the watchlist does not rank it. */
  symbol?: string | null;
  /** 1-based place on the ranked watchlist, when known. */
  rank?: number | null;
}

function SetupBlock({ row }: { row: SetupRow }) {
  const s = row.setup;
  const live = row.state === 'near' || row.state === 'armed' || row.state === 'triggered';
  const state = stateWords(row);
  const tape = tapeWords(row);
  return (
    <div className="cq-wl-setup" data-testid="watchlist-strip-setup">
      <div className="cq-wl-sub">Setup · {setupLabel(setupTypeOf(row)).toLowerCase()}</div>
      <dl className="cq-wl-kv">
        <dt>State</dt>
        <dd>
          <span className={`pillar-chip setups-state setups-state--${row.state}`} {...tipProps(state.tip, state.title)}>
            {state.text}
          </span>
        </dd>
        {live && s && (
          <>
            <dt>Trigger / stop</dt><dd className="num">{fmtPx(s.trigger)} / {fmtPx(s.stop)}</dd>
            <dt>Risk · target</dt><dd className="num">{fmtPx(s.risk)} · {fmtPx(s.target1)}</dd>
          </>
        )}
        {row.tape && (
          <>
            <dt>Tape</dt>
            <dd {...(tape ? tipProps(tape.tip, tape.title) : {})}>{TAPE_VERDICT_LABELS[row.tape.verdict] ?? row.tape.verdict}</dd>
          </>
        )}
        {row.grade && (<><dt>Grade</dt><dd>{row.grade}</dd></>)}
      </dl>
      {row.reason && <div className="cq-wl-reason">{row.reason}</div>}
    </div>
  );
}

function emptyText(loading: boolean, error: string | null, symbol: string, replay: PillarsReplay | null): string {
  if (error) return `${TICKER_WATCHLIST_STRIP_EMPTY} ${error}`;
  if (replay?.absent) return replayPillarsAbsent(symbol, replayMoment(replay), replay.absent);
  return loading ? WATCHLIST_STRIP_GRADING : TICKER_WATCHLIST_STRIP_EMPTY;
}

/** The board minute the grade read, else the playhead. */
function replayMoment(replay: PillarsReplay): string {
  return replayMomentLabel(replay.session_date, replay.minute_ts ?? replay.at);
}

function sourceText(source: string | null, rank: number | null, replay: PillarsReplay | null): string {
  if (replay) return replayPillarsSource(replayMoment(replay), replay.board, replay.board_source, replay.board_rank);
  if (source === 'watchlist' && rank) return watchlistStripRank(rank);
  return source ? WATCHLIST_STRIP_SOURCES[source] ?? '' : '';
}

export function TickerWatchlistStrip({ entry: ranked, symbol, rank = null }: Props) {
  const stream = useSetupsBoard();
  const { isAllowed, add, remove } = useBotAllowlist();
  const graded = useSymbolPillars(symbol ?? ranked?.symbol ?? null, ranked ?? null, rank);
  const entry = graded.entry;
  const setup = entry ? rowsBySymbol(stream?.board?.rows).get(entry.symbol)?.[0] : undefined;
  const allowed = entry ? isAllowed(entry.symbol) : false;
  const p = entry?.five_pillars;
  const source = sourceText(graded.source, graded.rank, graded.replay);
  return (
    <section className="cq-watchlist-strip" aria-label={TICKER_WATCHLIST_STRIP_TITLE} data-testid="watchlist-strip">
      <div className="cq-section-title">
        {TICKER_WATCHLIST_STRIP_TITLE}
        {p && <span className="cq-wl-count"> · {p.pass_count} / {p.total} pillars</span>}
      </div>
      {p && source ? <div className="cq-wl-source" data-testid="watchlist-strip-source">{source}</div> : null}
      {!entry || !p ? (
        <div className="cq-watchlist-strip-empty" data-testid="watchlist-strip-empty">
          {emptyText(graded.loading, graded.error, (symbol ?? ranked?.symbol ?? '').toUpperCase(), graded.replay)}
        </div>
      ) : (
        <>
          <ul className="cq-wl-pillars">
            {p.pillars.map(pc => (
              <li key={pc.name} className={pc.passed ? 'is-pass' : 'is-fail'}>
                <span className="cq-wl-mark">{pc.passed ? '✓' : '✗'}</span>
                <span>{WATCHLIST_PILLAR_NAMES[pc.name] ?? pc.name}</span>
                <span className="cq-wl-detail" title={pc.detail}>
                  {pc.name === 'catalyst' && entry.catalyst ? newsCell(entry).text : pc.detail}
                </span>
              </li>
            ))}
          </ul>
          {setup && <SetupBlock row={setup} />}
          <button
            type="button"
            className={`cq-wl-bot${allowed ? ' is-on' : ''}`}
            aria-pressed={allowed}
            title={allowed ? WATCHLIST_BOT_ON_TITLE : WATCHLIST_BOT_OFF_TITLE}
            onClick={() => void (allowed ? remove(entry.symbol) : add(entry.symbol))}
          >
            {allowed ? '● Bot trades it' : '○ Let the bot trade it'}
          </button>
        </>
      )}
    </section>
  );
}
