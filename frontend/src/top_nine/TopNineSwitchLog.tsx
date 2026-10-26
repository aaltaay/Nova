/** The bottom line: every switch on the list, newest first, so one missed while looking away is
 * still there. */
import { TickerLink } from '../components/TickerLink';
import { switchClock } from './topNineClock';
import { TOP_NINE_LOG_EMPTY, TOP_NINE_LOG_LABEL } from './topNineConstants';
import type { TopNineSwitch } from './topNineMarks';

export function TopNineSwitchLog({ log, onOpen }: { log: readonly TopNineSwitch[]; onOpen: (symbol: string) => void }) {
  return (
    <div className="top-nine-log" data-testid="top-nine-log">
      <span className="top-nine-log__label">{TOP_NINE_LOG_LABEL}</span>
      {log.length === 0 ? <span className="top-nine-log__empty">{TOP_NINE_LOG_EMPTY}</span> : null}
      {log.map((entry, i) => (
        <span key={`${entry.at}-${i}`} className="top-nine-log__entry">
          {i > 0 ? <span className="top-nine-log__sep" aria-hidden="true" /> : null}
          <span className="top-nine-log__time">{switchClock(entry)}</span>
          {entry.moves.map((m) => (
            <span key={m.symbol} className={`top-nine-log__move is-${m.kind}`}>
              <TickerLink symbol={m.symbol} onOpen={onOpen} look="own" className="top-nine-log__ticker" />
              {m.kind === 'new' ? ` new #${m.to}` : ` ${m.kind === 'up' ? '▲' : '▼'}${m.from}→${m.to}`}
            </span>
          ))}
          {entry.left.map((s) => (
            <span key={`left-${s}`} className="top-nine-log__move is-left">
              <TickerLink symbol={s} onOpen={onOpen} look="own" className="top-nine-log__ticker" /> left top 9
            </span>
          ))}
        </span>
      ))}
    </div>
  );
}
