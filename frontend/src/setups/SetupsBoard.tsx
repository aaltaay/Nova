/** The Setups board (ADR 022, ADR 031): one row per symbol and setup worth looking
 * at, nearest its trigger first, every cell said in the setup's own words and
 * explained on hover (ux/hoverTip.ts). "Stage ticket" fills the manual ticket
 * with the venue sleeve's risk per trade over the setup's risk a share, and
 * never places; a human presses Place. A proposal Nova itself takes, or one that
 * is not a trade, locks it with the reason (ADR 042 draft). */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { SETUP_COL_TIPS, SETUP_KIND_LABELS } from '../constants';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import { proposalStageLock, proposalStageSize } from './proposalVerdict';
import { fmtCents, fmtPx, fmtR, isActionable, outcomeLabel, rowClass, stagedLimit, tapeRank } from './setupsFormat';
import { gradeWords } from './pillarWords';
import { normalizeLiquidity, thinChip } from './liquidity';
import { riskSourceWords, type SleeveRisk } from './sleeveRisk';
import {
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
import { tf5Words } from './tf5Words';
import type { SetupRow } from './types';

interface BoardProps {
  rows: SetupRow[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  /** What an empty board says (the filter's setup, or every setup). */
  emptyText?: string;
  /** The venue sleeve's risk per trade: what a proposal's Stage sizes by. */
  risk: SleeveRisk;
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
  tf5: r => (r.tf5 ? (r.tf5.agrees ? 1 : 0) : null),
  r: r => (r.state === 'triggered' ? r.bar_r : null),
  why: r => r.reason,
};

/** A proposal's Stage on the board: sized by the sleeve's risk per trade, locked with its reason. */
function StageCell({ row, risk, onOpenTrading }: { row: SetupRow; risk: SleeveRisk; onOpenTrading: (s: string) => void }) {
  const p = row.proposal;
  if (!p) return null;
  const limit = stagedLimit(row);
  const size = proposalStageSize({ risk: p.risk ?? row.setup?.risk ?? null, entry: p.entry ?? row.setup?.entry ?? null,
    stop: p.stop ?? row.setup?.stop ?? null }, risk.riskUsd, `${riskSourceWords(risk)} risk per trade`);
  const lock = proposalStageLock({ ...p, entry: p.entry ?? row.setup?.entry ?? null }, size);
  const tip = `Stage a BUY limit at ${limit} for ${size.text} on this symbol's ticket. Stop ${fmtPx(row.setup?.stop)}. `
    + `Nothing is sent until you press Place.${risk.why ? `\n${risk.why}` : ''}`;
  return (
    <button
      type="button"
      className="setups-stage"
      disabled={lock !== null}
      {...whyProps(lock !== null, lock)}
      onClick={e => {
        e.stopPropagation();
        if (lock === null) stageSetupTicket(row.symbol, limit, onOpenTrading, size.qty);
      }}
      {...(lock === null ? tipProps(tip, 'Stage ticket') : {})}
      data-testid={`setups-stage-${row.symbol}`}
    >
      Stage ticket
    </button>
  );
}

function SetupBoardRow({ row, selected, onSelectSymbol, onOpenTrading, risk }: {
  row: SetupRow;
  selected: boolean;
  onSelectSymbol: (s: string) => void;
  onOpenTrading: (s: string) => void;
  risk: SleeveRisk;
}) {
  const s = row.setup;
  const state = stateWords(row);
  const trig = triggerWords(row);
  const toGo = toGoWords(row);
  const grade = gradeWords(row);
  const tf5 = tf5Words(row);
  const kind = kindWords(row);
  const broke = row.state === 'near' && Boolean(s?.detail?.broke_at);
  const thin = thinChip(normalizeLiquidity(row.liquidity));
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
        {thin && (
          <span className="pillar-chip setups-thin" {...tipProps(thin.tip, thin.title)} data-testid={`setups-thin-${row.symbol}`}>
            {thin.text}
          </span>
        )}
      </td>
      <td className="num" {...tipProps(trig.tip, trig.title)}>{s ? trig.text : '—'}</td>
      <td className="num">{fmtPx(s?.stop)}</td>
      <td className="num" {...tipProps('Entry minus the stop, per share: what one share risks.', 'Risk')}>{fmtCents(s?.risk)}</td>
      <td className="num">{fmtPx(s?.target1)}</td>
      <td className="num setups-distance" {...tipProps(toGo.tip, toGo.title)}>
        {row.state === 'triggered' ? outcomeLabel(row) : toGo.text === '·' ? '—' : toGo.text}
      </td>
      <td><TapeCell row={row} onOpenTrading={onOpenTrading} /></td>
      <td className="setups-grade" {...tipProps(grade.tip, grade.title)}>{grade.text === '·' ? '—' : grade.text}</td>
      <td>
        {tf5 ? (
          <span className={`setups-tf5 setups-tf5--${tf5.tone}`} {...tipProps(tf5.tip, tf5.title)}>{tf5.text}</span>
        ) : <span className="na-muted">—</span>}
      </td>
      <td className="num">{row.state === 'triggered' ? fmtR(row.bar_r) : '—'}</td>
      <td className="setups-reason" {...tipProps(row.reason, 'The scanner now')}>{row.reason}</td>
      <td>
        <StageCell row={row} risk={risk} onOpenTrading={onOpenTrading} />
      </td>
    </SelectableTableRow>
  );
}

export function SetupsBoard({ rows, selectedSymbol, onSelectSymbol, onOpenTrading, emptyText = EMPTY, risk }: BoardProps) {
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
            {head('tf5', '5m')}
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
              risk={risk}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
