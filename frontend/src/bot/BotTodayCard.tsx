/**
 * Today at a glance and the first-pullback scoreboard by the tape at the
 * trigger (ADR 022): scores, not fills -- the research exit rules on every
 * armed setup. Today's counts are the scoreboard's own (`days=1`); the open
 * proposals are the live board's.
 */
import { SETUPS_SPLIT_TITLES, TAPE_VERDICT_LABELS } from '../constants';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import { useSetupsScoreboard } from '../setups/useSetupsScoreboard';
import { fmtR } from './botsPageFormat';

const TAPES = ['go', 'wait', 'veto', 'blind'] as const;
const SCOREBOARD_DAYS = 5;

export function BotTodayCard() {
  const stream = useSetupsBoard();
  const board = stream?.board;
  const { data, error } = useSetupsScoreboard(true, SCOREBOARD_DAYS);
  const today = useSetupsScoreboard(true, 1).data?.summary?.all;
  const proposed = board?.proposals?.filter(p => p.status === 'open').length ?? 0;
  const byTape = data?.summary?.by?.tape_at_trigger ?? {};

  return (
    <section className="bots-card" data-testid="bots-today">
      <header className="bots-card__head">
        <h3>Today</h3>
        <span className="bots-card__sub">first pullback{board?.session_date ? ` · ${board.session_date}` : ''}</span>
      </header>
      <div className="bots-kpis">
        <div><span>Armed</span><b>{today ? today.armed : '—'}</b></div>
        <div><span>Triggered</span><b>{today ? today.triggered : '—'}</b></div>
        <div><span>Proposing now</span><b>{proposed}</b></div>
      </div>
      <header className="bots-card__head bots-card__head--sub">
        <h4>First pullback scoreboard</h4>
        <span className="bots-card__sub">last {SCOREBOARD_DAYS} days · {SETUPS_SPLIT_TITLES.tape_at_trigger?.toLowerCase() ?? 'by tape at the trigger'}</span>
      </header>
      {error ? <p className="bots-empty">{error}</p> : (
        <table className="bots-table" data-testid="bots-scoreboard">
          <thead><tr><th>Tape</th><th className="num">Triggered</th><th className="num">Win %</th><th className="num">Avg net R</th></tr></thead>
          <tbody>
            {TAPES.filter(t => byTape[t]).map(t => (
              <tr key={t}>
                <td><span className={`setups-tape--${t}`}>{(TAPE_VERDICT_LABELS[t] ?? t).replace('Tape: ', '').toUpperCase()}</span></td>
                <td className="num">{byTape[t].triggered}</td>
                <td className="num">{byTape[t].win_pct == null ? '—' : `${byTape[t].win_pct?.toFixed(0)}%`}</td>
                <td className="num">{fmtR(byTape[t].avg_net_r)}</td>
              </tr>
            ))}
            {TAPES.every(t => !byTape[t]) ? (
              <tr><td colSpan={4} className="bots-muted">{data ? 'No armed setup in these days yet.' : 'Loading…'}</td></tr>
            ) : null}
          </tbody>
        </table>
      )}
      <p className="bots-muted">Scores, not fills -- the research exit rules on every armed setup.</p>
    </section>
  );
}
