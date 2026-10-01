/**
 * Today at a glance and one setup's scoreboard by the tape at the trigger (approved
 * mockup v4, ADR 022, ADR 031, ADR 042). Each count says what it counts on hover:
 * armed / triggered are the picked setup's scoreboard counts for the day (its template
 * in play; scores, not trades); proposed counts every setup's proposals the audit
 * stream recorded that day; Nova's buys are the bot and Auto-entry against the sleeve's
 * cap; bot P&L is the bot's own fills in the practice ledger (a stated absence on Live).
 * The setup picker starts on the first setup at Strategy.
 */
import { useMemo, useState } from 'react';
import { BOT_SCANNER_SETUP_IDS } from '../constantGroups/bot';
import { SETUPS_SPLIT_TITLES } from '../constants';
import {
  BOTS_TODAY_ENTRIES_TIP,
  BOTS_TODAY_PNL_LIVE_TITLE,
  BOTS_TODAY_PNL_TIP,
  BOTS_TODAY_PROPOSED_TIP,
  BOTS_TODAY_SCOREBOARD_DAYS,
  BOTS_TODAY_SCOREBOARD_TITLE,
  BOTS_TODAY_SCORES_NOTE,
  BOTS_TODAY_SETUP_PICK,
  BOTS_TODAY_TITLE,
  BOTS_VENUE_LABELS,
  botsTodayArmedTip,
  botsTodayTriggeredTip,
} from '../constantGroups/bots_page';
import { todayPracticeDate } from '../account/accountFigures';
import { useSetupsScoreboard } from '../setups/useSetupsScoreboard';
import type { Scoreboard } from '../setups';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { tipProps } from '../ux/hoverTip';
import { setupLabelOf } from './botLevels';
import { fmtR, fmtUsdCents } from './botsPageFormat';
import type { BotsVenue } from './useBotsVenue';
import type { BotAuditEntry, BotEntriesToday } from './types';

const TAPES = ['go', 'wait', 'veto', 'blind'] as const;
const TAPE_NAMES: Record<string, string> = { go: 'GO', wait: 'WAIT', veto: 'NO', blind: 'BLIND' };

interface TapeLine {
  tape: (typeof TAPES)[number];
  stats: Scoreboard['summary']['all'];
}

/** The Tape column sorts GO, WAIT, NO, BLIND (the card's own order) and back; the rest by their numbers. */
const COLUMNS: SortColumns<TapeLine> = {
  tape: l => TAPES.length - TAPES.indexOf(l.tape),
  triggered: l => l.stats.triggered,
  win: l => l.stats.win_pct,
  net_r: l => l.stats.avg_net_r,
};

/** Setup proposals the audit stream recorded on `day` (practice-day date). */
export function proposedOn(audit: readonly BotAuditEntry[], day: string): number {
  return audit.filter(a => a.action === 'setup_proposal' && a.outcome === 'proposed'
    && todayPracticeDate(new Date(a.timestamp * 1000)) === day).length;
}

export function BotTodayCard({ venue, audit, botPnl, entries, firstAtStrategy }: {
  venue: BotsVenue;
  audit: BotAuditEntry[];
  botPnl: number | null;
  /** Nova's automatic entries today on this venue (bot + Auto-entry), against the sleeve's cap. */
  entries?: BotEntriesToday;
  /** The setup the counts start on: the first at Strategy, else the first pullback. */
  firstAtStrategy?: string | null;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const setup = picked ?? firstAtStrategy ?? BOT_SCANNER_SETUP_IDS[0];
  const name = setupLabelOf(setup);
  const { data, error } = useSetupsScoreboard(true, BOTS_TODAY_SCOREBOARD_DAYS, setup);
  const today = useSetupsScoreboard(true, 1, setup).data?.summary?.all;
  const byTape = data?.summary?.by?.tape_at_trigger;
  const lines = useMemo<TapeLine[]>(
    () => TAPES.flatMap(t => (byTape?.[t] ? [{ tape: t, stats: byTape[t] }] : [])),
    [byTape],
  );
  const { rows: sorted, sort, onSort } = useTableSort('bot.today_scoreboard', lines, COLUMNS);
  const where = venue.venue ? `${BOTS_VENUE_LABELS[venue.venue]} day ${venue.today}` : venue.today;
  const pnlTone = botPnl == null ? '' : botPnl > 0 ? ' is-up' : botPnl < 0 ? ' is-down' : '';

  return (
    <section className="bots-card" data-testid="bots-today">
      <header className="bots-card__head">
        <h3>{BOTS_TODAY_TITLE}</h3>
        <span className="bots-card__sub">{where}</span>
      </header>
      <label className="bots-today__pick">
        <span className="bots-muted">{BOTS_TODAY_SETUP_PICK}</span>
        <select data-testid="bots-today-setup" value={setup} onChange={e => setPicked(e.target.value)}>
          {BOT_SCANNER_SETUP_IDS.map(id => <option key={id} value={id}>{setupLabelOf(id)}</option>)}
        </select>
      </label>
      <div className="bots-kpis bots-kpis--today">
        <div {...tipProps(botsTodayArmedTip(name), `${name} · armed`)}>
          <span>Armed</span><b data-testid="bots-kpi-armed">{today ? today.armed : '—'}</b><small>{name}</small>
        </div>
        <div {...tipProps(botsTodayTriggeredTip(name), `${name} · triggered`)}>
          <span>Triggered</span><b data-testid="bots-kpi-triggered">{today ? today.triggered : '—'}</b><small>{name}</small>
        </div>
        <div {...tipProps(BOTS_TODAY_PROPOSED_TIP, 'Proposed · every setup')}>
          <span>Proposed</span><b data-testid="bots-kpi-proposed">{proposedOn(audit, venue.today)}</b><small>every setup</small>
        </div>
        <div {...tipProps(BOTS_TODAY_ENTRIES_TIP, 'Nova buys')}>
          <span>Nova buys</span>
          <b data-testid="bots-kpi-entries">{entries ? `${entries.count} / ${entries.cap}` : '—'}</b><small>bot + Auto-entry</small>
        </div>
        <div {...tipProps(venue.practiceVenue ? BOTS_TODAY_PNL_TIP : BOTS_TODAY_PNL_LIVE_TITLE, 'Bot P&L')}>
          <span>Bot P&amp;L</span><b className={pnlTone} data-testid="bots-kpi-pnl">{fmtUsdCents(botPnl)}</b><small>its own fills</small>
        </div>
      </div>
      <header className="bots-card__head bots-card__head--sub">
        <h4>{BOTS_TODAY_SCOREBOARD_TITLE(name)}</h4>
        <span className="bots-card__sub">
          last {BOTS_TODAY_SCOREBOARD_DAYS} days · {(SETUPS_SPLIT_TITLES.tape_at_trigger ?? 'Tape at the trigger').toLowerCase()}
        </span>
      </header>
      {error ? <p className="bots-empty">{error}</p> : (
        <table className="bots-table" data-testid="bots-scoreboard">
          <thead>
            <tr>
              <SortTh col="tape" sort={sort} onSort={onSort}>Tape</SortTh>
              <SortTh col="triggered" sort={sort} onSort={onSort} className="num">Triggered</SortTh>
              <SortTh col="win" sort={sort} onSort={onSort} className="num">Win %</SortTh>
              <SortTh col="net_r" sort={sort} onSort={onSort} className="num">Avg net R</SortTh>
            </tr>
          </thead>
          <tbody>
            {sorted.map(({ tape: t, stats }) => {
              const r = stats.avg_net_r;
              return (
                <tr key={t}>
                  <td><span className={`bots-vbadge bots-vbadge--${t}`}>{TAPE_NAMES[t]}</span></td>
                  <td className="num">{stats.triggered}</td>
                  <td className="num">{stats.win_pct == null ? '—' : `${stats.win_pct.toFixed(0)}%`}</td>
                  <td className={`num${r == null ? '' : r > 0 ? ' is-up' : r < 0 ? ' is-down' : ''}`}>{fmtR(r)}</td>
                </tr>
              );
            })}
            {lines.length === 0 ? (
              <tr><td colSpan={4} className="bots-muted">{data ? 'No armed setup in these days yet.' : 'Loading…'}</td></tr>
            ) : null}
          </tbody>
        </table>
      )}
      <p className="bots-foot-note">{BOTS_TODAY_SCORES_NOTE}</p>
    </section>
  );
}
