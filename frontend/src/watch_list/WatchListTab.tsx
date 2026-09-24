/**
 * The Watch list tab: the symbols the operator picked by hand, each with its
 * board row's market facts (when a board holds it) and today's newest HOD Momo
 * or Running Up alert -- what the toast announces. Remove from here, add by
 * ticker here or from any ticker row. Nothing here places an order.
 */
import { useMemo, useState, type FormEvent } from 'react';
import { ScannerRowNumCell, ScannerRowNumHeader } from '../components/ScannerTableChrome';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { fmtStripClock, stripAlertMs, useHodMomoOptional, type AlertObject } from '../hod_momo';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import type { ScannerRow } from '../types/scanner';
import { fmtPct, fmtPrice, fmtVolume, pctToneClass } from '../utils/quoteFormat';
import { WatchEyeIcon } from './WatchEyeIcon';
import {
  WATCH_LIST_ADD_BUTTON,
  WATCH_LIST_ADD_INVALID,
  WATCH_LIST_ADD_PLACEHOLDER,
  WATCH_LIST_CELL_ABSENT,
  WATCH_LIST_EMPTY,
  WATCH_LIST_HOD_COLUMN_TITLE,
  WATCH_LIST_NO_HOD_TODAY,
  WATCH_LIST_NOT_ON_BOARD,
  WATCH_LIST_TAB_NOTE,
  watchListRemoveTitle,
} from './watchListConstants';
import { addToWatchList, removeFromWatchList, useWatchList } from './watchListStore';
import type { WatchListBoards } from './types';
import './watchList.css';

const BOARD_LABELS: ReadonlyArray<[keyof WatchListBoards, string]> = [
  ['gainers', 'Gainers'],
  ['gappers', 'Gappers'],
  ['losers', 'Losers'],
  ['afterhours', 'After Hours'],
  ['largeCap', 'Large Cap'],
];

export interface BoardHit {
  row: ScannerRow;
  board: string;
}

/** Pure: symbol -> the first board row that carries it. */
export function boardRowsBySymbol(boards: WatchListBoards): Map<string, BoardHit> {
  const out = new Map<string, BoardHit>();
  for (const [key, label] of BOARD_LABELS) {
    for (const row of boards[key]) {
      const symbol = row.symbol.toUpperCase();
      if (!out.has(symbol)) out.set(symbol, { row, board: label });
    }
  }
  return out;
}

export interface HodToday {
  latest: AlertObject;
  count: number;
}

/** Pure: symbol -> its newest HOD Momo feed alert (Running Up included) and how many it had; alerts arrive newest first. */
export function hodAlertsBySymbol(alerts: readonly AlertObject[]): Map<string, HodToday> {
  const out = new Map<string, HodToday>();
  for (const alert of alerts) {
    const symbol = String(alert.ticker ?? '').toUpperCase();
    if (!symbol) continue;
    const seen = out.get(symbol);
    if (seen) seen.count += 1;
    else out.set(symbol, { latest: alert, count: 1 });
  }
  return out;
}

/** IBKR's prior close as the price is no trade (QA C50): no price, no change. */
function traded(row: ScannerRow | undefined): ScannerRow | undefined {
  return row && row.quote_quality !== 'close_fallback' ? row : undefined;
}

function ChangeCell({ row }: { row: ScannerRow | undefined }) {
  // IBKR's prior close as the price has no change yet (QA C50): a dash, never 0%.
  if (!row || row.quote_quality === 'close_fallback' || row.change_pct == null) {
    return <span className="na-muted">{WATCH_LIST_CELL_ABSENT}</span>;
  }
  return <span className={pctToneClass(row.change_pct)}>{fmtPct(row.change_pct, WATCH_LIST_CELL_ABSENT)}</span>;
}

function HodCell({ hod }: { hod: HodToday | undefined }) {
  if (!hod) return <span className="na-muted">{WATCH_LIST_NO_HOD_TODAY}</span>;
  return (
    <span className="watch-list__hod" title={`${hod.count} HOD Momo / Running Up alert${hod.count === 1 ? '' : 's'} today`}>
      <b>{fmtStripClock(hod.latest)}</b> {hod.latest.strategy_name}
      {hod.count > 1 ? <span className="na-muted"> ({hod.count})</span> : null}
    </span>
  );
}

function AddSymbolForm() {
  const [text, setText] = useState('');
  const [invalid, setInvalid] = useState(false);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    if (addToWatchList(text)) {
      setText('');
      setInvalid(false);
    } else {
      setInvalid(true);
    }
  };
  return (
    <form className="watch-list__add" onSubmit={submit} data-testid="watch-list-add">
      <input
        type="text"
        value={text}
        placeholder={WATCH_LIST_ADD_PLACEHOLDER}
        aria-label={WATCH_LIST_ADD_PLACEHOLDER}
        aria-invalid={invalid}
        spellCheck={false}
        autoComplete="off"
        data-testid="watch-list-add-input"
        onChange={e => {
          setText(e.target.value.toUpperCase());
          setInvalid(false);
        }}
      />
      <button type="submit" data-testid="watch-list-add-submit">{WATCH_LIST_ADD_BUTTON}</button>
      {invalid ? <span className="watch-list__invalid" role="alert">{WATCH_LIST_ADD_INVALID}</span> : null}
    </form>
  );
}

interface Props {
  boards: WatchListBoards;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function WatchListTab({ boards, selectedSymbol, onSelectSymbol, onOpenTrading }: Props) {
  const symbols = useWatchList();
  const hod = useHodMomoOptional();
  const alerts = hod?.stream.alerts;
  const { gainers, gappers, losers, afterhours, largeCap } = boards;
  const byBoard = useMemo(
    () => boardRowsBySymbol({ gainers, gappers, losers, afterhours, largeCap }),
    [gainers, gappers, losers, afterhours, largeCap],
  );
  const byHod = useMemo(() => hodAlertsBySymbol(alerts ?? []), [alerts]);
  const columns = useMemo<SortColumns<string>>(() => ({
    symbol: symbol => symbol,
    last: symbol => traded(byBoard.get(symbol)?.row)?.price,
    change: symbol => traded(byBoard.get(symbol)?.row)?.change_pct,
    volume: symbol => byBoard.get(symbol)?.row.volume,
    board: symbol => byBoard.get(symbol)?.board,
    // The newest alert first.
    hod: symbol => {
      const hit = byHod.get(symbol);
      return hit ? stripAlertMs(hit.latest) : null;
    },
  }), [byBoard, byHod]);
  const { rows: sorted, sort, onSort } = useTableSort('watch_list.symbols', symbols, columns);

  return (
    <div className="watch-list" data-testid="watch-list-tab">
      <div className="watch-list__toolbar">
        <p className="watch-list__note">
          <WatchEyeIcon className="watch-list__note-eye" /> {WATCH_LIST_TAB_NOTE}
        </p>
        <AddSymbolForm />
      </div>
      {symbols.length === 0 ? (
        <div className="empty-state" data-testid="watch-list-empty">{WATCH_LIST_EMPTY}</div>
      ) : (
        <div className="table-wrapper">
          <table className="watch-list__grid">
            <thead>
              <tr>
                <ScannerRowNumHeader />
                <SortTh col="symbol" sort={sort} onSort={onSort} title="Click the row for the side panel. Click the ticker to open Trader.">Symbol</SortTh>
                <SortTh col="last" sort={sort} onSort={onSort} className="num">Last</SortTh>
                <SortTh col="change" sort={sort} onSort={onSort} className="num" title="Change against the prior close">% Chg</SortTh>
                <SortTh col="volume" sort={sort} onSort={onSort} className="num">Volume</SortTh>
                <SortTh col="board" sort={sort} onSort={onSort} title="The scanner board the facts come from">Board</SortTh>
                <SortTh col="hod" sort={sort} onSort={onSort} title={WATCH_LIST_HOD_COLUMN_TITLE}>HOD Momo today</SortTh>
                <th aria-label="Remove" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((symbol, index) => {
                const hit = byBoard.get(symbol);
                const row = hit?.row;
                const closeFallback = row?.quote_quality === 'close_fallback';
                return (
                  <SelectableTableRow
                    key={symbol}
                    symbol={symbol}
                    selected={selectedSymbol === symbol}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    openOnRowClick={false}
                    symbolMenu
                  >
                    <ScannerRowNumCell index={index} />
                    <td>
                      <SymbolSelectButton
                        symbol={symbol}
                        selected={selectedSymbol === symbol}
                        onSelect={onSelectSymbol}
                        onOpenTrading={onOpenTrading}
                      />
                    </td>
                    <td className="num">
                      {row && !closeFallback && row.price != null ? fmtPrice(row.price) : <span className="na-muted">{WATCH_LIST_CELL_ABSENT}</span>}
                    </td>
                    <td className="num"><ChangeCell row={row} /></td>
                    <td className="num">
                      {row?.volume != null ? fmtVolume(row.volume) : <span className="na-muted">{WATCH_LIST_CELL_ABSENT}</span>}
                    </td>
                    <td>{hit ? hit.board : <span className="na-muted">{WATCH_LIST_NOT_ON_BOARD}</span>}</td>
                    <td><HodCell hod={byHod.get(symbol)} /></td>
                    <td className="watch-list__remove-cell">
                      <button
                        type="button"
                        className="watch-list__remove"
                        title={watchListRemoveTitle(symbol)}
                        aria-label={watchListRemoveTitle(symbol)}
                        data-testid={`watch-list-remove-${symbol}`}
                        onClick={e => {
                          e.stopPropagation();
                          removeFromWatchList(symbol);
                        }}
                      >
                        ×
                      </button>
                    </td>
                  </SelectableTableRow>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
