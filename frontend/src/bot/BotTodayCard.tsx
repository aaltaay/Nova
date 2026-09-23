/**
 * Today at a glance and the first-pullback scoreboard by the tape at the
 * trigger (approved mockup v4, ADR 022). Armed / triggered are the
 * scoreboard's own counts for the day; proposed counts the proposals the
 * audit stream recorded that day; bot P&L is the bot's own fills in the
 * practice ledger (a stated absence on Live). Scores, not fills.
 */
import { SETUPS_SPLIT_TITLES } from '../constants';
import {
  BOTS_TODAY_BOT_ONLY,
  BOTS_TODAY_PNL_LIVE_TITLE,
  BOTS_TODAY_SCOREBOARD_DAYS,
  BOTS_TODAY_SCOREBOARD_TITLE,
  BOTS_TODAY_SCORES_NOTE,
  BOTS_TODAY_TITLE,
  BOTS_VENUE_LABELS,
} from '../constantGroups/bots_page';
import { todayPracticeDate } from '../account/accountFigures';
import { useSetupsScoreboard } from '../setups/useSetupsScoreboard';
import { fmtR, fmtUsdCents } from './botsPageFormat';
import type { BotsVenue } from './useBotsVenue';
import type { BotAuditEntry } from './types';

const TAPES = ['go', 'wait', 'veto', 'blind'] as const;
const TAPE_NAMES: Record<string, string> = { go: 'GO', wait: 'WAIT', veto: 'NO', blind: 'BLIND' };

/** Setup proposals the audit stream recorded on `day` (practice-day date). */
export function proposedOn(audit: readonly BotAuditEntry[], day: string): number {
  return audit.filter(a => a.action === 'setup_proposal' && a.outcome === 'proposed'
    && todayPracticeDate(new Date(a.timestamp * 1000)) === day).length;
}

export function BotTodayCard({ venue, audit, botPnl }: { venue: BotsVenue; audit: BotAuditEntry[]; botPnl: number | null }) {
  const { data, error } = useSetupsScoreboard(true, BOTS_TODAY_SCOREBOARD_DAYS);
  const today = useSetupsScoreboard(true, 1).data?.summary?.all;
  const byTape = data?.summary?.by?.tape_at_trigger ?? {};
  const where = venue.venue ? `${BOTS_VENUE_LABELS[venue.venue]} day ${venue.today}` : venue.today;
  const pnlTone = botPnl == null ? '' : botPnl > 0 ? ' is-up' : botPnl < 0 ? ' is-down' : '';

  return (
    <section className="bots-card" data-testid="bots-today">
      <header className="bots-card__head">
        <h3>{BOTS_TODAY_TITLE}</h3>
        <span className="bots-card__sub">{BOTS_TODAY_BOT_ONLY} · {where}</span>
      </header>
      <div className="bots-kpis">
        <div><span>Armed</span><b data-testid="bots-kpi-armed">{today ? today.armed : '—'}</b></div>
        <div><span>Triggered</span><b data-testid="bots-kpi-triggered">{today ? today.triggered : '—'}</b></div>
        <div><span>Proposed</span><b data-testid="bots-kpi-proposed">{proposedOn(audit, venue.today)}</b></div>
        <div title={venue.practiceVenue ? undefined : BOTS_TODAY_PNL_LIVE_TITLE}>
          <span>Bot P&amp;L</span><b className={pnlTone} data-testid="bots-kpi-pnl">{fmtUsdCents(botPnl)}</b>
        </div>
      </div>
      <header className="bots-card__head bots-card__head--sub">
        <h4>{BOTS_TODAY_SCOREBOARD_TITLE}</h4>
        <span className="bots-card__sub">
          last {BOTS_TODAY_SCOREBOARD_DAYS} days · {(SETUPS_SPLIT_TITLES.tape_at_trigger ?? 'Tape at the trigger').toLowerCase()}
        </span>
      </header>
      {error ? <p className="bots-empty">{error}</p> : (
        <table className="bots-table" data-testid="bots-scoreboard">
          <thead><tr><th>Tape</th><th className="num">Triggered</th><th className="num">Win %</th><th className="num">Avg net R</th></tr></thead>
          <tbody>
            {TAPES.filter(t => byTape[t]).map(t => {
              const r = byTape[t].avg_net_r;
              return (
                <tr key={t}>
                  <td><span className={`bots-vbadge bots-vbadge--${t}`}>{TAPE_NAMES[t]}</span></td>
                  <td className="num">{byTape[t].triggered}</td>
                  <td className="num">{byTape[t].win_pct == null ? '—' : `${byTape[t].win_pct?.toFixed(0)}%`}</td>
                  <td className={`num${r == null ? '' : r > 0 ? ' is-up' : r < 0 ? ' is-down' : ''}`}>{fmtR(r)}</td>
                </tr>
              );
            })}
            {TAPES.every(t => !byTape[t]) ? (
              <tr><td colSpan={4} className="bots-muted">{data ? 'No armed setup in these days yet.' : 'Loading…'}</td></tr>
            ) : null}
          </tbody>
        </table>
      )}
      <p className="bots-foot-note">{BOTS_TODAY_SCORES_NOTE}</p>
    </section>
  );
}
