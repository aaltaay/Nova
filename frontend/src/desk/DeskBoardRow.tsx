/**
 * One Desk board row. Click opens the symbol beside the board (the row is the
 * open), double-click pops it out to the full Trader, right-click opens the
 * symbol menu. The watch eye and REC / bot dots follow the watch list, the
 * recorder and the allowlist; the hover actions are the watch list toggle and
 * the existing capture and allowlist calls. Nothing here invents a figure: unknown is a dash.
 */
import { memo, type KeyboardEvent, type MouseEvent } from 'react';
import { openBotSymbolMenu } from '../bot';
import { ScannerRowNumCell } from '../components/ScannerTableChrome';
import { scannerColClass } from '../components/scannerTableCol';
import {
  DESK_ACTION_ALLOWLIST,
  DESK_ACTION_ALLOWLIST_SHORT,
  DESK_ACTION_ALLOWLIST_TITLE,
  DESK_ACTION_RECORD,
  DESK_ACTION_RECORD_SHORT,
  DESK_ACTION_RECORD_TITLE,
  DESK_ACTION_STOP_RECORD,
  DESK_ACTION_STOP_RECORD_SHORT,
  DESK_ACTION_STOP_RECORD_TITLE,
  DESK_ACTION_UNLIST,
  DESK_ACTION_UNLIST_SHORT,
  DESK_ACTION_UNLIST_TITLE,
  DESK_CELL_ABSENT,
  DESK_DOT_BOT_HELD_TITLE,
  DESK_DOT_BOT_QUIET_TITLE,
  DESK_DOT_REC_TITLE,
  DESK_HEADLINE_NONE,
  DESK_ROW_TITLE,
  DESK_STATE_ABSENT_TITLE,
} from '../constantGroups/desk';
import { formatSignedPct, pctTone } from '../stock_view/tabContext';
import { fmtVolume } from '../utils/quoteFormat';
import {
  toggleWatchList,
  useIsWatched,
  WATCH_ACTION_WATCH,
  WATCH_ACTION_WATCH_TITLE,
  WATCH_ACTION_WATCHING,
  WATCH_ACTION_WATCHING_TITLE,
  WatchEyeIcon,
  WatchMark,
} from '../watch_list';
import { fmtRelVol, headlineClockEt, type DeskBoardRow as Row } from './deskBoardRows';

/**
 * Why Record and Allowlist are off on this board -- the sample desk's (#449),
 * which records no feed and plays no bot; absent means both work. (Watch works
 * everywhere: the sample desk keeps a watch list of its own.)
 */
export interface DeskActionLocks {
  record: string;
  allowlist: string;
}

export interface DeskBoardRowProps {
  row: Row;
  index: number;
  selected: boolean;
  /** 0-100, the gap bar against the widest gap on the board. */
  barPct: number;
  recording: boolean;
  allowed: boolean;
  /** Allowlisted and this desk holds the depth line (recording or a live tab). */
  held: boolean;
  stale: boolean;
  flash?: 'up' | 'down';
  onOpen: (symbol: string) => void;
  onPopOut: (symbol: string) => void;
  onRecord: (symbol: string, start: boolean) => void;
  onAllowlist: (symbol: string, add: boolean) => void;
  actionLocks?: DeskActionLocks | null;
}

function stop(event: MouseEvent): void {
  event.stopPropagation();
}

/** The full label, plus the short one the narrow board swaps in (deskBoard.css). */
function ActLabel({ full, short }: { full: string; short: string }) {
  return (
    <>
      <span className="desk-board__act-text">{full}</span>
      <span className="desk-board__act-text desk-board__act-text--short" aria-hidden="true">{short}</span>
    </>
  );
}

function DeskBoardRowImpl({
  row, index, selected, barPct, recording, allowed, held, stale, flash,
  onOpen, onPopOut, onRecord, onAllowlist, actionLocks = null,
}: DeskBoardRowProps) {
  const sym = row.symbol;
  const watched = useIsWatched(sym);
  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(sym);
    }
  };
  const clock = headlineClockEt(row.headlineAt);
  const tone = pctTone(row.gapPct);
  return (
    <tr
      className={`selectable-row desk-board__row${selected ? ' row-selected' : ''}`}
      data-testid={`desk-board-row-${sym}`}
      aria-selected={selected}
      tabIndex={0}
      title={DESK_ROW_TITLE}
      onClick={() => onOpen(sym)}
      onDoubleClick={() => onPopOut(sym)}
      onKeyDown={onKeyDown}
      onContextMenu={(event) => {
        event.preventDefault();
        openBotSymbolMenu(sym, event.clientX, event.clientY);
      }}
    >
      <ScannerRowNumCell index={index} />
      <td className={scannerColClass('symbol')}>
        <span className="desk-board__sym">{sym}</span>
        <span className="desk-board__dots">
          <WatchMark symbol={sym} />
          {recording && (
            <i className="desk-board__dot desk-board__dot--rec" title={DESK_DOT_REC_TITLE} data-testid={`desk-board-rec-${sym}`} />
          )}
          {allowed && (
            <i
              className={`desk-board__dot desk-board__dot--bot${held ? '' : ' desk-board__dot--quiet'}`}
              title={held ? DESK_DOT_BOT_HELD_TITLE : DESK_DOT_BOT_QUIET_TITLE}
              data-testid={`desk-board-bot-${sym}`}
              data-held={held ? '1' : '0'}
            />
          )}
        </span>
      </td>
      <td className={`${scannerColClass('price')}${stale ? ' is-stale' : ''}${flash ? ` flash-${flash}` : ''}`} data-testid={`desk-board-price-${sym}`}>
        {row.price != null ? row.price.toFixed(2) : DESK_CELL_ABSENT}
      </td>
      <td className={scannerColClass('gap_percent')}>
        <span className="desk-board__gap">
          <b className={`desk-board__gap-num desk-board__gap-num--${tone}`}>{row.gapPct != null ? formatSignedPct(row.gapPct) : DESK_CELL_ABSENT}</b>
          <span className="desk-board__bar" aria-hidden="true">
            <i className={`desk-board__bar-fill desk-board__bar-fill--${tone}`} style={{ width: `${barPct}%` }} data-testid={`desk-board-bar-${sym}`} />
          </span>
        </span>
      </td>
      <td className={scannerColClass('volume')}>{fmtVolume(row.volume)}</td>
      <td className={scannerColClass('rel_volume')}>{fmtRelVol(row.relVolume)}</td>
      <td className={scannerColClass('float')}>{fmtVolume(row.float)}</td>
      <td className={scannerColClass('catalyst')}>
        {row.catalyst ? (
          <>
            <span className="desk-board__chip" title={row.headline ?? row.catalyst}>{row.catalyst}</span>
            {clock && <span className="desk-board__chip-time">{clock}</span>}
          </>
        ) : (
          <span className="desk-board__none">{DESK_HEADLINE_NONE}</span>
        )}
      </td>
      <td className={`${scannerColClass('state')} desk-board__state`}>
        <span className="desk-board__none" title={DESK_STATE_ABSENT_TITLE}>{DESK_CELL_ABSENT}</span>
        <span className="desk-board__acts" onDoubleClick={stop}>
          <button
            type="button"
            className={`desk-board__act${watched ? ' desk-board__act--watching' : ''}`}
            title={watched ? WATCH_ACTION_WATCHING_TITLE : WATCH_ACTION_WATCH_TITLE}
            aria-label={watched ? WATCH_ACTION_WATCHING : WATCH_ACTION_WATCH}
            aria-pressed={watched}
            data-testid={`desk-board-watch-${sym}`}
            onClick={(event) => { stop(event); toggleWatchList(sym); }}
          >
            <WatchEyeIcon />
            <ActLabel full={watched ? WATCH_ACTION_WATCHING : WATCH_ACTION_WATCH} short={WATCH_ACTION_WATCH} />
          </button>
          <button
            type="button"
            className={`desk-board__act${recording ? ' desk-board__act--rec' : ''}`}
            title={actionLocks ? '' : recording ? DESK_ACTION_STOP_RECORD_TITLE : DESK_ACTION_RECORD_TITLE}
            aria-label={recording ? DESK_ACTION_STOP_RECORD : DESK_ACTION_RECORD}
            data-testid={`desk-board-record-${sym}`}
            disabled={Boolean(actionLocks)}
            data-why={actionLocks?.record}
            onClick={(event) => { stop(event); if (!actionLocks) onRecord(sym, !recording); }}
          >
            <i className="desk-board__dot desk-board__dot--rec" aria-hidden="true" />
            <ActLabel
              full={recording ? DESK_ACTION_STOP_RECORD : DESK_ACTION_RECORD}
              short={recording ? DESK_ACTION_STOP_RECORD_SHORT : DESK_ACTION_RECORD_SHORT}
            />
          </button>
          <button
            type="button"
            className="desk-board__act"
            title={actionLocks ? '' : allowed ? DESK_ACTION_UNLIST_TITLE : DESK_ACTION_ALLOWLIST_TITLE}
            aria-label={allowed ? DESK_ACTION_UNLIST : DESK_ACTION_ALLOWLIST}
            data-testid={`desk-board-allowlist-${sym}`}
            disabled={Boolean(actionLocks)}
            data-why={actionLocks?.allowlist}
            onClick={(event) => { stop(event); if (!actionLocks) onAllowlist(sym, !allowed); }}
          >
            <ActLabel
              full={allowed ? DESK_ACTION_UNLIST : DESK_ACTION_ALLOWLIST}
              short={allowed ? DESK_ACTION_UNLIST_SHORT : DESK_ACTION_ALLOWLIST_SHORT}
            />
          </button>
        </span>
      </td>
    </tr>
  );
}

export const DeskBoardRow = memo(DeskBoardRowImpl);
