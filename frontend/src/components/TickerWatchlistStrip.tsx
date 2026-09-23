/** The selected ticker's watchlist read in the side panel: the Five Pillars with their
 * reasons, where the first-pullback scanner has it, and the bot allowlist toggle. */
import {
  SETUP_STATE_LABELS,
  TAPE_VERDICT_LABELS,
  TICKER_WATCHLIST_STRIP_EMPTY,
  TICKER_WATCHLIST_STRIP_TITLE,
  WATCHLIST_BOT_OFF_TITLE,
  WATCHLIST_BOT_ON_TITLE,
  WATCHLIST_PILLAR_NAMES,
} from '../constants';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import { fmtPx } from '../setups/setupsFormat';
import type { SetupRow } from '../setups/types';
import type { WatchlistEntry } from '../strategy/types';
import { newsCell } from '../strategy/watchlistFormat';

interface Props {
  entry: WatchlistEntry | null | undefined;
}

function SetupBlock({ row }: { row: SetupRow }) {
  const s = row.setup;
  const live = row.state === 'near' || row.state === 'armed' || row.state === 'triggered';
  return (
    <div className="cq-wl-setup" data-testid="watchlist-strip-setup">
      <div className="cq-wl-sub">Setup · first pullback</div>
      <dl className="cq-wl-kv">
        <dt>State</dt>
        <dd><span className={`pillar-chip setups-state setups-state--${row.state}`}>{SETUP_STATE_LABELS[row.state] ?? row.state}</span></dd>
        {live && s && (
          <>
            <dt>Trigger / stop</dt><dd className="num">{fmtPx(s.trigger)} / {fmtPx(s.stop)}</dd>
            <dt>Risk · target</dt><dd className="num">{fmtPx(s.risk)} · {fmtPx(s.target1)}</dd>
          </>
        )}
        {row.tape && (
          <>
            <dt>Tape</dt>
            <dd title={row.tape.reasons.join('\n')}>{TAPE_VERDICT_LABELS[row.tape.verdict] ?? row.tape.verdict}</dd>
          </>
        )}
        {row.grade && (<><dt>Grade</dt><dd>{row.grade}</dd></>)}
      </dl>
      {row.reason && <div className="cq-wl-reason">{row.reason}</div>}
    </div>
  );
}

export function TickerWatchlistStrip({ entry }: Props) {
  const stream = useSetupsBoard();
  const { isAllowed, add, remove } = useBotAllowlist();
  const setup = entry ? stream?.board?.rows.find(r => r.symbol === entry.symbol) : undefined;
  const allowed = entry ? isAllowed(entry.symbol) : false;
  const p = entry?.five_pillars;
  return (
    <section className="cq-watchlist-strip" aria-label={TICKER_WATCHLIST_STRIP_TITLE}>
      <div className="cq-section-title">
        {TICKER_WATCHLIST_STRIP_TITLE}
        {p && <span className="cq-wl-count"> · {p.pass_count} / {p.total} pillars</span>}
      </div>
      {!entry || !p ? (
        <div className="cq-watchlist-strip-empty">{TICKER_WATCHLIST_STRIP_EMPTY}</div>
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
            {allowed ? '● On bot allowlist' : '○ Add to bot allowlist'}
          </button>
        </>
      )}
    </section>
  );
}
