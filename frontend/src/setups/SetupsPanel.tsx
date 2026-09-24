/** Watchlist > Setups (ADR 022): the live first-pullback scanner and its
 * scoreboard. The bot reads the tape and proposes; it never places. */
import { useEffect, useState } from 'react';
import { SetupsBoard } from './SetupsBoard';
import { SetupsScoreboard } from './SetupsScoreboard';
import { useSetupsBoard } from './SetupsStreamContext';
import { isSetupsSoundEnabled, setSetupsSoundEnabled, subscribeSetupsSound } from './setupsSound';
import { useSetupsScoreboard } from './useSetupsScoreboard';
import type { SetupsBoard as Board } from './types';
import './setups.css';

interface Props {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

type View = 'board' | 'scoreboard';

function simLine(board: Board): string {
  const r = board.replay;
  const what = `Sim eyes on ${r?.symbol ?? 'the replay'}${r?.date ? ` ${r.date}` : ''}`;
  if (r?.note) return `${what} · ${r.note}`;
  if (r?.error) return `${what} · the recording could not be read: ${r.error}`;
  if (r?.loading) return `${what} · reading the recording\u2026`;
  return `${what} · following the playhead${board.template ? ` · template ${board.template.name}` : ''}`;
}

function statusLine(board: Board | null, connected: boolean): string {
  if (!connected) return 'Connecting to the setup scanner\u2026';
  if (!board) return 'Waiting for the first board\u2026';
  if (board.source === 'sim') return simLine(board);
  const parts = [`Watching ${board.universe} symbol${board.universe === 1 ? '' : 's'} from the HOD Momo list`];
  if (board.template) {
    const others = (board.templates_watched ?? 1) - 1;
    parts.push(`template ${board.template.name}${others > 0 ? ` (+${others} scored alongside)` : ''}`);
  }
  if (board.seeding > 0) parts.push(`loading today's bars for ${board.seeding}`);
  if (!board.proposing) parts.push('no proposals on a replay desk');
  return parts.join(' · ');
}

function useSoundSwitch(): [boolean, (next: boolean) => void] {
  const [on, setOn] = useState(isSetupsSoundEnabled);
  useEffect(() => subscribeSetupsSound(setOn), []);
  return [on, setSetupsSoundEnabled];
}

export function SetupsPanel({ selectedSymbol, onSelectSymbol, onOpenTrading }: Props) {
  const stream = useSetupsBoard();
  const board = stream?.board ?? null;
  const connected = stream?.connected ?? false;
  const [view, setView] = useState<View>('board');
  const [days, setDays] = useState(5);
  const [sound, setSound] = useSoundSwitch();
  const score = useSetupsScoreboard(view === 'scoreboard', days);

  return (
    <div className="setups-panel">
      <div className="watchlist-description">
        One scanner for the first pullback: a fresh 5% leg to a new high, one to three red candles that
        hold the 9 EMA and half the leg, then a trigger over the last pullback candle&rsquo;s high. Near
        the trigger the bot reads Level 2 and the tape and proposes only when it says go. It never
        places: &ldquo;Stage ticket&rdquo; fills the ticket, and you press Place.
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
        <span className={`setups-status${connected ? '' : ' setups-status--down'}`}>{statusLine(board, connected)}</span>
        <button
          type="button"
          className="setups-link"
          onClick={() => setSound(!sound)}
          title={sound ? 'Mute the proposal ping (the alert card still shows)' : 'Ping when the bot raises a proposal'}
        >
          {sound ? 'Sound on' : 'Sound off'}
        </button>
      </div>
      {!stream && (
        <div className="empty-state">The setup scanner runs in the main desk window, not in a pop-out.</div>
      )}
      {stream && board?.scoreboard_error && (
        <div className="empty-state">The scoreboard is not recording: {board.scoreboard_error}</div>
      )}
      {stream && view === 'board' && (
        <SetupsBoard
          rows={board?.rows ?? []}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
      )}
      {stream && view === 'scoreboard' && (
        <SetupsScoreboard data={score.data} error={score.error} loading={score.loading} days={days} onDays={setDays} />
      )}
    </div>
  );
}
