/** Watchlist > Setups (ADR 022, ADR 031): every setup's live scanner on one board,
 * a chip per setup to filter it, and each setup's own scoreboard. The bot reads
 * the tape and proposes; it never places. */
import { useEffect, useState } from 'react';
import { BOT_SETUP_IDS, BOT_SETUP_NEXT } from '../constantGroups/bot';
import { SETUPS_FILTER_ALL, SETUPS_FILTER_TIP } from '../constantGroups/setups';
import { tipProps } from '../ux/hoverTip';
import { SetupsBoard } from './SetupsBoard';
import { SetupsScoreboard } from './SetupsScoreboard';
import { useSetupsBoard } from './SetupsStreamContext';
import { ALL_SETUPS, useSetupsFilter } from './setupsBoardFilter';
import { isSetupsSoundEnabled, setSetupsSoundEnabled, subscribeSetupsSound } from './setupsSound';
import { FIRST_PULLBACK, setupLabel, setupShort, setupTypeOf } from './setupWords';
import { useSetupsScoreboard } from './useSetupsScoreboard';
import type { SetupsBoard as Board, SetupSummary } from './types';
import './setups.css';

interface Props {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

type View = 'board' | 'scoreboard';

function simLine(board: Board, summary: SetupSummary | null): string {
  const r = board.replay;
  const what = `Sim eyes on ${r?.symbol ?? 'the replay'}${r?.date ? ` ${r.date}` : ''}`;
  if (r?.note) return `${what} · ${r.note}`;
  if (r?.error) return `${what} · the recording could not be read: ${r.error}`;
  if (r?.loading) return `${what} · reading the recording…`;
  return `${what} · following the playhead${summary?.template ? ` · template ${summary.template.name}` : ''}`;
}

function proposingWords(board: Board): string {
  const setups = board.setups ?? [];
  if (board.proposing) {
    const eyes = setups.filter(s => s.proposing).map(s => setupShort(s.id).toLowerCase());
    return eyes.length ? `proposing: ${eyes.join(', ')}` : 'proposing';
  }
  if (setups.some(s => s.level >= 1)) return 'no proposals on a replay desk';
  return 'every setup at Off: scoring in silence';
}

function statusLine(board: Board | null, connected: boolean, summary: SetupSummary | null): string {
  if (!connected) return 'Connecting to the setup scanner…';
  if (!board) return 'Waiting for the first board…';
  if (board.source === 'sim') return simLine(board, summary);
  const parts = [`Watching ${board.universe} symbol${board.universe === 1 ? '' : 's'} from the HOD Momo list`];
  if (summary?.template) {
    const others = (summary.templates_watched ?? 1) - 1;
    parts.push(`${setupShort(summary.id)} template ${summary.template.name}${others > 0 ? ` (+${others} scored alongside)` : ''}`);
  } else if (board.setups?.length) {
    parts.push(`${board.setups.length} setups`);
  }
  if (board.seeding > 0) parts.push(`loading today's bars for ${board.seeding}`);
  parts.push(proposingWords(board));
  return parts.join(' · ');
}

function useSoundSwitch(): [boolean, (next: boolean) => void] {
  const [on, setOn] = useState(isSetupsSoundEnabled);
  useEffect(() => subscribeSetupsSound(setOn), []);
  return [on, setSetupsSoundEnabled];
}

/** The setups the board carries: the API's list, else (schema 1) the first pullback. */
function scannedSetups(board: Board | null): string[] {
  if (board?.setups?.length) return board.setups.map(s => s.id);
  return [FIRST_PULLBACK];
}

export function SetupsPanel({ selectedSymbol, onSelectSymbol, onOpenTrading }: Props) {
  const stream = useSetupsBoard();
  const board = stream?.board ?? null;
  const connected = stream?.connected ?? false;
  const [view, setView] = useState<View>('board');
  const [days, setDays] = useState(5);
  const [sound, setSound] = useSoundSwitch();
  const [filter, setFilter] = useSetupsFilter();
  const scanned = scannedSetups(board);
  const active = filter !== ALL_SETUPS && scanned.includes(filter) ? filter : ALL_SETUPS;
  const allRows = board?.rows ?? [];
  const rows = active === ALL_SETUPS ? allRows : allRows.filter(r => setupTypeOf(r) === active);
  const summary = (board?.setups ?? []).find(s => s.id === active) ?? null;
  const chosen = (board?.setups ?? []).find(s => s.chosen)?.id ?? FIRST_PULLBACK;
  const scoreSetup = active === ALL_SETUPS ? chosen : active;
  const score = useSetupsScoreboard(view === 'scoreboard', days, scoreSetup);
  const countOf = (id: string) => allRows.filter(r => setupTypeOf(r) === id).length;
  const emptyText = active === ALL_SETUPS
    ? undefined
    : `No ${setupLabel(active).toLowerCase()} setups right now. Rows show up as soon as a name starts the pattern.`;

  return (
    <div className="setups-panel">
      <div className="watchlist-description">
        One scanner per setup — first pullback, bull flag, flat-top breakout and red to green — on the HOD Momo
        names. Near the trigger the bot reads Level 2 and the tape; a setup at Eyes proposes only when it says go.
        It never places: &ldquo;Stage ticket&rdquo; fills the ticket, and you press Place. Hover any chip for what it means.
      </div>
      <div className="setups-toolbar">
        <button type="button" className={`sub-tab ${view === 'board' ? 'active' : ''}`} onClick={() => setView('board')}>
          Board
        </button>
        <button
          type="button"
          className={`sub-tab ${view === 'scoreboard' ? 'active' : ''}`}
          onClick={() => setView('scoreboard')}
        >
          Scoreboard
        </button>
        <span className={`setups-status${connected ? '' : ' setups-status--down'}`}>{statusLine(board, connected, summary)}</span>
        <button
          type="button"
          className="setups-link"
          onClick={() => setSound(!sound)}
          title={sound ? 'Mute the proposal ping (the alert card still shows)' : 'Ping when the bot raises a proposal'}
        >
          {sound ? 'Sound on' : 'Sound off'}
        </button>
      </div>
      <div className="setups-filter" role="radiogroup" aria-label="Setup" data-testid="setups-filter">
        <button type="button" role="radio" aria-checked={active === ALL_SETUPS}
          className={`setups-chip${active === ALL_SETUPS ? ' is-on' : ''}`} data-testid="setups-filter-all"
          onClick={() => setFilter(ALL_SETUPS)} {...tipProps(SETUPS_FILTER_TIP(SETUPS_FILTER_ALL, allRows.length), SETUPS_FILTER_ALL)}>
          {SETUPS_FILTER_ALL} <b>{allRows.length}</b>
        </button>
        {BOT_SETUP_IDS.map(id => {
          const live = scanned.includes(id);
          const why = live ? null : BOT_SETUP_NEXT[id]?.head ?? 'No scanner yet';
          const n = countOf(id);
          return (
            <button key={id} type="button" role="radio" aria-checked={active === id}
              className={`setups-chip${active === id ? ' is-on' : ''}${live ? '' : ' is-off'}`}
              data-testid={`setups-filter-${id}`} disabled={!live} data-why={why ?? undefined}
              onClick={() => setFilter(id)} {...(live ? tipProps(SETUPS_FILTER_TIP(setupLabel(id), n), setupLabel(id)) : {})}>
              {live ? <>{setupShort(id)} <b>{n}</b></> : `${setupShort(id)}: ${why?.replace(/^Not watching: /, '')}`}
            </button>
          );
        })}
      </div>
      {!stream && (
        <div className="empty-state">The setup scanner runs in the main desk window, not in a pop-out.</div>
      )}
      {stream && board?.scoreboard_error && (
        <div className="empty-state">The scoreboard is not recording: {board.scoreboard_error}</div>
      )}
      {stream && view === 'board' && (
        <SetupsBoard
          rows={rows}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
          emptyText={emptyText}
        />
      )}
      {stream && view === 'scoreboard' && (
        <SetupsScoreboard data={score.data} error={score.error} loading={score.loading} days={days} onDays={setDays}
          setup={scoreSetup} />
      )}
    </div>
  );
}
