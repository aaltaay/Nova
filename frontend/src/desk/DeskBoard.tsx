/**
 * The Desk board: the Scanner condensed to one column beside the Trader's
 * workspace. Header = list picker (any registry tab module);
 * one headline line for the selected row; the rows through the shared scanner
 * table shell with an explicit compact column set (issue #276 lock); footer =
 * `N of M · board freezes at the open` and the dots legend.
 *
 * Presentational: DeskPage wires the feed, the recorder, the allowlist and the
 * workspace. Absences are stated, never rendered as an empty table.
 */
import { useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import { ScannerColGroup, ScannerRowNumHeader } from '../components/ScannerTableChrome';
import { listAbsenceText } from '../scanner/listAbsence';
import { replayListAbsence } from '../leaderboard/leaderboardRows';
import { SCANNER_TABLE_WRAPPER_CLASS, scannerColClass } from '../components/scannerTableCol';
import {
  DESK_BOARD_ARIA,
  DESK_BOARD_COLUMNS,
  DESK_BOARD_COLUMN_TITLE,
  DESK_BOARD_FREEZE_LISTS,
  DESK_BOARD_FREEZE_NOTE,
  DESK_BOARD_NO_FEED,
  DESK_BOARD_PICK_ARIA,
  DESK_BOARD_PICK_TITLE,
  DESK_HEADLINE_NONE,
  DESK_HEADLINE_NO_ROW,
  DESK_LEGEND_BOT_HELD,
  DESK_LEGEND_BOT_QUIET,
  DESK_LEGEND_REC,
  deskBoardCount,
  deskBoardEmpty,
  deskBoardHiddenByFilter,
  deskBoardNotMirrored,
  deskHeadlineTextAbsent,
} from '../constantGroups/desk';
import { isRowQuoteStale } from '../hooks/useScannerPriceStream';
import type { LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { ScannerRow } from '../types/scanner';
import { listTabModules, type NovaModule } from '../workspace/registry';
import { DeskBoardRow } from './DeskBoardRow';
import { deskBoardRowsFor, deskHeadlineFor, gapBarPct, maxAbsGap } from './deskBoardRows';
import './deskBoard.css';

export interface DeskBoardProps {
  feed: LiveScannerFeed | null;
  list: string;
  onListChange: (list: string) => void;
  /** Registry tab modules the picker offers (visibility already applied). */
  modules?: NovaModule[];
  /** Row driving the workspace: the active tab, else the selected symbol. */
  selectedSymbol: string | null;
  recordingSymbols: readonly string[];
  isAllowed: (symbol: string) => boolean;
  /** Live Trader tabs -- with a recording, the proxy for "this desk holds the depth line". */
  liveTabs: readonly string[];
  filterRows?: <T extends ScannerRow>(rows: T[]) => T[];
  onOpen: (symbol: string) => void;
  onPopOut: (symbol: string) => void;
  onRecord: (symbol: string, start: boolean) => void;
  onAllowlist: (symbol: string, add: boolean) => void;
}

export function DeskBoard({
  feed, list, onListChange, modules, selectedSymbol, recordingSymbols, isAllowed, liveTabs,
  filterRows, onOpen, onPopOut, onRecord, onAllowlist,
}: DeskBoardProps) {
  // Only scanner lists -- a page (Bots, Account) is not a board list (QA V30).
  const options = useMemo(
    () => (modules ?? listTabModules()).filter(m => m.navGroup != null),
    [modules],
  );
  const module = options.find(m => m.id === list) ?? options[0];
  const title = module?.title ?? list;
  const board = useMemo(() => deskBoardRowsFor(list, feed, filterRows), [list, feed, filterRows]);
  const rows = board?.rows ?? null;
  const widest = useMemo(() => (rows ? maxAbsGap(rows) : 0), [rows]);
  const selected = selectedSymbol?.trim().toUpperCase() ?? null;
  const headline = useMemo(() => deskHeadlineFor(selected, feed), [selected, feed]);
  const recording = useMemo(() => new Set(recordingSymbols.map(s => s.toUpperCase())), [recordingSymbols]);
  const live = useMemo(() => new Set(liveTabs.map(s => s.toUpperCase())), [liveTabs]);
  const hidden = board ? board.total - board.rows.length : 0;

  return (
    <section className="panel desk-board" aria-label={DESK_BOARD_ARIA} data-testid="desk-board" data-list={list}>
      <header className="desk-board__head">
        <label className="desk-board__pick-wrap" title={DESK_BOARD_PICK_TITLE}>
          <span className="desk-board__title" data-testid="desk-board-list-label">{title}</span>
          {rows && <span className="desk-board__count" data-testid="desk-board-count">{rows.length}</span>}
          <ChevronDown size={12} aria-hidden="true" />
          <select
            className="desk-board__pick"
            aria-label={DESK_BOARD_PICK_ARIA}
            data-testid="desk-board-pick"
            value={module?.id ?? list}
            onChange={event => onListChange(event.target.value)}
          >
            {options.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
        </label>
      </header>

      <div className="desk-board__headline" data-testid="desk-board-headline">
        {!selected ? (
          <span className="desk-board__none">{DESK_HEADLINE_NO_ROW}</span>
        ) : headline?.text ? (
          <>
            {headline.clock && <span className="desk-board__headline-time">{headline.clock}</span>}
            <span className="desk-board__headline-sym">{selected}</span>
            <span className="desk-board__headline-text" title={headline.text}>{headline.text}</span>
            {headline.source && <span className="desk-board__headline-src">{headline.source}</span>}
          </>
        ) : headline?.clock ? (
          <>
            <span className="desk-board__headline-sym">{selected}</span>
            <span className="desk-board__none">{deskHeadlineTextAbsent(headline.clock)}</span>
          </>
        ) : (
          <>
            <span className="desk-board__headline-sym">{selected}</span>
            <span className="desk-board__none">{DESK_HEADLINE_NONE}</span>
          </>
        )}
      </div>

      <div className={`${SCANNER_TABLE_WRAPPER_CLASS} desk-board__table`}>
        {!feed ? (
          <p className="desk-board__absent" data-testid="desk-board-absent">{DESK_BOARD_NO_FEED}</p>
        ) : rows == null ? (
          <p className="desk-board__absent" data-testid="desk-board-absent">{deskBoardNotMirrored(title)}</p>
        ) : rows.length === 0 ? (
          <p className="desk-board__absent" data-testid="desk-board-absent">
            {feed.replay
              ? replayListAbsence(feed.replay, list)
              : listAbsenceText(title, { restError: feed.restError, healthStatus: feed.health?.status }, deskBoardEmpty)}
          </p>
        ) : (
          <table>
            <ScannerColGroup columns={DESK_BOARD_COLUMNS} />
            <thead>
              <tr>
                <ScannerRowNumHeader />
                {DESK_BOARD_COLUMNS.map(([key, label]) => (
                  <th key={key} data-col={key} className={scannerColClass(key)} title={DESK_BOARD_COLUMN_TITLE[key] ?? label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const rec = recording.has(row.symbol);
                const allowed = isAllowed(row.symbol);
                return (
                  <DeskBoardRow
                    key={row.symbol}
                    row={row}
                    index={index}
                    selected={row.symbol === selected}
                    barPct={gapBarPct(row.gapPct, widest)}
                    recording={rec}
                    allowed={allowed}
                    held={allowed && (rec || live.has(row.symbol))}
                    stale={!feed.replay && isRowQuoteStale(row.symbol, feed.rowQuoteTs, feed.now, feed.pricesStale)}
                    flash={feed.flashSymbols[row.symbol]}
                    onOpen={onOpen}
                    onPopOut={onPopOut}
                    onRecord={onRecord}
                    onAllowlist={onAllowlist}
                  />
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <footer className="desk-board__foot" data-testid="desk-board-foot">
        {board && (
          <span className="desk-board__foot-count">{deskBoardCount(board.rows.length, board.total)}</span>
        )}
        {hidden > 0 && <span className="desk-board__foot-warn">{deskBoardHiddenByFilter(hidden)}</span>}
        {DESK_BOARD_FREEZE_LISTS.includes(list) && <span>{DESK_BOARD_FREEZE_NOTE}</span>}
        <span className="desk-board__legend">
          <span><i className="desk-board__dot desk-board__dot--rec" aria-hidden="true" />{DESK_LEGEND_REC}</span>
          <span><i className="desk-board__dot desk-board__dot--bot" aria-hidden="true" />{DESK_LEGEND_BOT_HELD}</span>
          <span><i className="desk-board__dot desk-board__dot--bot desk-board__dot--quiet" aria-hidden="true" />{DESK_LEGEND_BOT_QUIET}</span>
        </span>
      </footer>
    </section>
  );
}
