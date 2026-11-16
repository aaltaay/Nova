/** Contenders > Setups (ADR 022, ADR 031): every setup's live scanner on one board,
 * a chip per setup to filter it, and each setup's own scoreboard. Since ADR 072 every
 * strategy only watches, on Level 1: nothing proposes and nothing buys, and the board
 * says so. "Stage ticket" only fills a ticket, sized by the venue sleeve's risk per trade. */
import { useEffect, useState } from 'react';
import { BOT_SETUP_IDS, BOT_SETUP_NEXT } from '../constantGroups/bot';
import { SETUPS_FILTER_ALL, SETUPS_FILTER_TIP, SETUPS_LEVEL_WORDS } from '../constantGroups/setups';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { DESK_MUTE_REASON, useDeskMuted } from '../sound';
import { tipProps } from '../ux/hoverTip';
import { SetupsBoard } from './SetupsBoard';
import { SetupsScoreboard } from './SetupsScoreboard';
import { useSetupsBoard } from './SetupsStreamContext';
import { ALL_SETUPS, useSetupsFilter } from './setupsBoardFilter';
import { isSetupsSoundEnabled, setSetupsSoundEnabled, subscribeSetupsSound } from './setupsSound';
import { FIRST_PULLBACK, setupLabel, setupShort, setupTypeOf } from './setupWords';
import { recordedEmptyText, simBoardLine, simBoardTip } from './simBoardWords';
import { useSleeveRisk } from './sleeveRisk';
import { useSetupsScoreboard } from './useSetupsScoreboard';
import type { SetupsBoard as Board, SetupSummary } from './types';
import './setups.css';

interface Props {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

type View = 'board' | 'scoreboard';

/** ADR 072: no strategy proposes or trades; the line says what the board is. */
const WATCH_ONLY_WORDS = 'watching only: no strategy trades';

function statusLine(board: Board | null, connected: boolean, summary: SetupSummary | null): string {
  if (!connected) return 'Connecting to the setup scanner…';
  if (!board) return 'Waiting for the first board…';
  if (board.source === 'sim') return simBoardLine(board, summary);
  const parts = [`Watching ${board.universe} symbol${board.universe === 1 ? '' : 's'} from the HOD Momo list`];
  if (summary?.template) {
    const others = (summary.templates_watched ?? 1) - 1;
    parts.push(`${setupShort(summary.id)} template ${summary.template.name}${others > 0 ? ` (+${others} scored alongside)` : ''}`);
  } else if (board.setups?.length) {
    parts.push(`${board.setups.length} setups`);
  }
  if (board.seeding > 0) parts.push(`loading today's bars for ${board.seeding}`);
  parts.push(WATCH_ONLY_WORDS);
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

/** The scoreboard's setup with "All" picked: the highest level (Strategy first; the chosen setup is retired,
 * ADR 042 draft), else the first pullback. */
function leadingSetup(board: Board | null): string {
  const setups = [...(board?.setups ?? [])].sort((a, b) => (b.level ?? 0) - (a.level ?? 0));
  return setups[0] && (setups[0].level ?? 0) > 0 ? setups[0].id : FIRST_PULLBACK;
}

export function SetupsPanel({ selectedSymbol, onSelectSymbol, onOpenTrading }: Props) {
  const stream = useSetupsBoard();
  const board = stream?.board ?? null;
  const connected = stream?.connected ?? false;
  const [view, setView] = useState<View>('board');
  const [days, setDays] = useState(5);
  const [sound, setSound] = useSoundSwitch();
  const deskMuted = useDeskMuted();
  const [filter, setFilter] = useSetupsFilter();
  const scanned = scannedSetups(board);
  const active = filter !== ALL_SETUPS && scanned.includes(filter) ? filter : ALL_SETUPS;
  const allRows = board?.rows ?? [];
  const rows = active === ALL_SETUPS ? allRows : allRows.filter(r => setupTypeOf(r) === active);
  const summary = (board?.setups ?? []).find(s => s.id === active) ?? null;
  const scoreSetup = active === ALL_SETUPS ? leadingSetup(board) : active;
  const score = useSetupsScoreboard(view === 'scoreboard', days, scoreSetup);
  const sample = useSampleDataOptional();
  // A proposal's Stage sizes by the desk venue's risk per trade: read it while the board shows.
  const risk = useSleeveRisk(null, Boolean(stream) && view === 'board' && !sample);
  const countOf = (id: string) => allRows.filter(r => setupTypeOf(r) === id).length;
  const emptyText = recordedEmptyText(board) ?? (active === ALL_SETUPS
    ? undefined
    : `No ${setupLabel(active).toLowerCase()} setups right now. Rows show up as soon as a name starts the pattern.`);

  return (
    <div className="setups-panel">
      <div className="watchlist-description" data-testid="setups-description">
        One scanner per setup on the HOD Momo names: the long ones (first pullback, bull flag, flat-top breakout, red
        to green, Gap and Go) and the five shorts, marked ▼.
        {' '}{SETUPS_LEVEL_WORDS} &ldquo;Stage ticket&rdquo; only fills your ticket, sized by your risk per trade: a
        short goes in on its Short side with its buy stop. You press Place. Hover any chip for what it means.
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
        <span className={`setups-status${connected ? '' : ' setups-status--down'}`}
          data-testid="setups-status" {...(board?.source === 'sim' ? tipProps(simBoardTip(board)) : {})}>
          {statusLine(board, connected, summary)}
        </span>
        <button
          type="button"
          className="setups-link"
          onClick={() => setSound(!sound)}
          title={deskMuted ? DESK_MUTE_REASON
            : sound ? 'Mute the proposal ping (the alert card still shows)' : 'Ping when the bot raises a proposal'}
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
          risk={risk}
        />
      )}
      {stream && view === 'scoreboard' && (
        <SetupsScoreboard data={score.data} error={score.error} loading={score.loading} days={days} onDays={setDays}
          setup={scoreSetup} />
      )}
    </div>
  );
}
