/** The Setups board (ADR 022, ADR 031): one row per symbol and setup worth looking
 * at, nearest its trigger first, every cell said in the setup's own words and
 * explained on hover (ux/hoverTip.ts). Signal only -- "Stage ticket" fills the
 * manual ticket and never places; a human presses Place. */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { SETUP_COL_TIPS, SETUP_KIND_LABELS, SETUPS_STAGE_NO_ENTRY_WHY } from '../constants';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { tipProps } from '../ux/hoverTip';
import { fmtCents, fmtPx, fmtR, isActionable, outcomeLabel, rowClass, stagedLimit, tapeRank } from './setupsFormat';
import {
  gradeWords,
  rowRank,
  setupLabel,
  setupShort,
  setupTypeOf,
  stateWords,
  tapeWords,
  toGoWords,
  triggerWords,
} from './setupWords';
import { stageSetupTicket } from './stageSetupTicket';
import type { SetupRow } from './types';

interface BoardProps {
  rows: SetupRow[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  /** What an empty board says (the filter's setup, or every setup). */
  emptyText?: string;
}

const EMPTY = 'No setups right now. Every scanner watches the HOD Momo names on one-minute bars and lists a symbol once it starts its pattern.';

function TapeCell({ row, onOpenTrading }: { row: SetupRow; onOpenTrading: (s: string) => void }) {
  const tape = tapeWords(row);
  if (!tape) return <span className="na-muted">—</span>;
  const verdict = row.tape?.verdict;
  return (
    <span className="setups-tape">
      <span className={`pillar-chip setups-tape--${verdict ?? 'none'}`} {...tipProps(tape.tip, tape.title)}>
        {tape.text}
      </span>
      {verdict === 'blind' && (
        <button
          type="button"
          className="setups-link"
          onClick={e => { e.stopPropagation(); onOpenTrading(row.symbol); }}
          {...tipProps('Open this symbol in the Trader. Its Level 2 line lets the bot read the tape here.', 'Open L2')}
        >
          Open L2
        </button>
      )}
    </span>
  );
}

function kindWords(row: SetupRow): { text: string; tip: string } {
  const type = setupTypeOf(row);
  const second = Boolean(row.kind?.startsWith('second_'));
  const kind = row.kind ? SETUP_KIND_LABELS[row.kind] ?? row.kind : setupLabel(type);
  return {
    text: second ? `${setupShort(type)} · 2nd` : setupShort(type),
    tip: `${kind}: ${second ? 'the second of this setup on the symbol today (the read-out counts only the first)' : 'the first of this setup on the symbol today'}.`,
  };
}

/** What each header sorts on: the levels as prices, the state and the tape by how far along they are. */
const COLUMNS: SortColumns<SetupRow> = {
  symbol: r => r.symbol,
  setup: r => kindWords(r).text,
  // The most advanced first: near, armed, triggered, ... (rowRank is lowest-first).
  state: r => -rowRank(r),
  trigger: r => r.setup?.trigger,
  stop: r => r.setup?.stop,
  risk: r => r.setup?.risk,
  target: r => r.setup?.target1,
  // Nearest the trigger first; a triggered row shows how it went, not a distance.
  to_go: { value: r => (isActionable(r) && r.setup ? r.distance : null), first: 'asc' },
  tape: tapeRank,
  grade: r => r.grade,
  r: r => (r.state === 'triggered' ? r.bar_r : null),
  why: r => r.reason,
};

function SetupBoardRow({ row, selected, onSelectSymbol, onOpenTrading }: {
  row: SetupRow;
  selected: boolean;
  onSelectSymbol: (s: string) => void;
  onOpenTrading: (s: string) => void;
}) {
  const s = row.setup;
  const state = stateWords(row);
  const trig = triggerWords(row);
  const toGo = toGoWords(row);
  const grade = gradeWords(row);
  const kind = kindWords(row);
  const broke = row.state === 'near' && Boolean(s?.detail?.broke_at);
  const limit = stagedLimit(row);
  return (
    <SelectableTableRow
      symbol={row.symbol}
      selected={selected}
      onSelect={onSelectSymbol}
      onOpenTrading={onOpenTrading}
      openOnRowClick={false}
      symbolMenu
      rowTitle={false}
      className={rowClass(row)}
    >
      <td>
        <SymbolSelectButton symbol={row.symbol} selected={selected} onSelect={onSelectSymbol} onOpenTrading={onOpenTrading} />
      </td>
      <td className="setups-kind" {...tipProps(kind.tip, setupLabel(setupTypeOf(row)))}>{kind.text}</td>
      <td>
        <span className={`pillar-chip setups-state setups-state--${broke ? 'broke' : row.state}`} {...tipProps(state.tip, state.title)}>
          {state.text}
        </span>
      </td>
      <td className="num" {...tipProps(trig.tip, trig.title)}>{s ? trig.text : '—'}</td>
      <td className="num">{fmtPx(s?.stop)}</td>
      <td className="num" {...tipProps('Entry minus the stop, per share: what one share risks.', 'Risk')}>{fmtCents(s?.risk)}</td>
      <td className="num">{fmtPx(s?.target1)}</td>
      <td className="num setups-distance" {...tipProps(toGo.tip, toGo.title)}>
        {row.state === 'triggered' ? outcomeLabel(row) : toGo.text === '·' ? '—' : toGo.text}
      </td>
      <td><TapeCell row={row} onOpenTrading={onOpenTrading} /></td>
      <td {...tipProps(grade.tip, grade.title)}>{row.grade ?? '—'}</td>
      <td className="num">{row.state === 'triggered' ? fmtR(row.bar_r) : '—'}</td>
      <td className="setups-reason" {...tipProps(row.reason, 'The scanner now')}>{row.reason}</td>
      <td>
        {row.proposal ? (
          <button
            type="button"
            className="setups-stage"
            disabled={!limit}
            data-why={limit ? undefined : SETUPS_STAGE_NO_ENTRY_WHY}
            onClick={e => { e.stopPropagation(); stageSetupTicket(row.symbol, limit, onOpenTrading); }}
            {...(limit ? tipProps(`Stage a BUY limit at ${limit} on this symbol's ticket. Stop ${fmtPx(s?.stop)}. Nothing is sent until you press Place.`, 'Stage ticket') : {})}
          >
            Stage ticket
          </button>
        ) : null}
      </td>
    </SelectableTableRow>
  );
}

export function SetupsBoard({ rows, selectedSymbol, onSelectSymbol, onOpenTrading, emptyText = EMPTY }: BoardProps) {
  const { rows: sorted, sort, onSort } = useTableSort('setups.board', rows, COLUMNS);
  if (rows.length === 0) {
    return <div className="empty-state">{emptyText}</div>;
  }
  // A column without a tip of its own reads the shared one (SETUP_COL_TIPS) under its key.
  const head = (col: string, label: string, num = false, tip?: string) => (
    <SortTh col={col} sort={sort} onSort={onSort} className={num ? 'num' : undefined} {...tipProps(tip ?? SETUP_COL_TIPS[col], label)}>
      {label}
    </SortTh>
  );
  return (
    <div className="table-wrapper setups-table">
      <table>
        <thead>
          <tr>
            {head('symbol', 'Symbol')}
            {head('setup', 'Setup', false, 'Which setup\'s scanner holds the row. One symbol can sit in two setups; each is scored on its own.')}
            {head('state', 'State')}
            {head('trigger', 'Trigger', true)}
            {head('stop', 'Stop', true, 'Where the setup is wrong: the pullback, flag or base low, or the low since the open.')}
            {head('risk', 'Risk', true, 'Entry minus the stop, per share.')}
            {head('target', 'Target', true, 'Target 1: half comes off there and the stop moves to the entry.')}
            {head('to_go', 'To go', true)}
            {head('tape', 'Tape')}
            {head('grade', 'Grade')}
            {head('r', 'R', true, 'What the research exit rules made of a triggered setup, in R (gross) -- a score, not a fill.')}
            {head('why', 'Why', false, 'The scanner\'s own words for where the setup is now.')}
            <th />
          </tr>
        </thead>
        <tbody>
          {sorted.map(row => (
            <SetupBoardRow
              key={`${row.symbol}-${setupTypeOf(row)}`}
              row={row}
              selected={selectedSymbol === row.symbol}
              onSelectSymbol={onSelectSymbol}
              onOpenTrading={onOpenTrading}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
