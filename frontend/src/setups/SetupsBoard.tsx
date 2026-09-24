/** The Setups board (ADR 022): one row per symbol worth looking at, nearest to
 * its trigger first. Signal only -- "Stage ticket" fills the manual ticket and
 * never places; a human presses Place. */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import {
  SETUP_KIND_LABELS,
  SETUP_STATE_LABELS,
  SETUP_STATE_TITLES,
  TAPE_VERDICT_LABELS,
  TAPE_VERDICT_TITLES,
} from '../constants';
import {
  catalystTitle, distanceLabel, fmtCents, fmtPx, fmtR, isActionable, outcomeLabel, rowClass, stagedLimit,
} from './setupsFormat';
import { stageSetupTicket } from './stageSetupTicket';
import type { SetupRow } from './types';

interface BoardProps {
  rows: SetupRow[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

function TapeCell({ row, onOpenTrading }: { row: SetupRow; onOpenTrading: (s: string) => void }) {
  if (!isActionable(row)) return <span className="na-muted">—</span>;
  const tape = row.tape;
  if (!tape) return <span className="na-muted">—</span>;
  const title = [TAPE_VERDICT_TITLES[tape.verdict], ...(tape.reasons ?? [])].filter(Boolean).join('\n');
  return (
    <span className="setups-tape">
      <span className={`pillar-chip setups-tape--${tape.verdict}`} title={title}>
        {TAPE_VERDICT_LABELS[tape.verdict] ?? tape.verdict}
      </span>
      {tape.verdict === 'blind' && (
        <button
          type="button"
          className="setups-link"
          onClick={() => onOpenTrading(row.symbol)}
          title="Open this symbol in the Trader. Its Level 2 line lets the bot read the tape here."
        >
          Open L2
        </button>
      )}
    </span>
  );
}

function SetupBoardRow({ row, selected, onSelectSymbol, onOpenTrading }: {
  row: SetupRow;
  selected: boolean;
  onSelectSymbol: (s: string) => void;
  onOpenTrading: (s: string) => void;
}) {
  const s = row.setup;
  const r = s?.risk ?? null;
  return (
    <SelectableTableRow
      symbol={row.symbol}
      selected={selected}
      onSelect={onSelectSymbol}
      onOpenTrading={onOpenTrading}
      openOnRowClick={false}
      symbolMenu
      className={rowClass(row)}
    >
      <td>
        <SymbolSelectButton symbol={row.symbol} selected={selected} onSelect={onSelectSymbol} onOpenTrading={onOpenTrading} />
      </td>
      <td>
        <span className={`pillar-chip setups-state setups-state--${row.state}`} title={`${SETUP_STATE_TITLES[row.state] ?? ''}\n${row.reason}`}>
          {SETUP_STATE_LABELS[row.state] ?? row.state}
        </span>
      </td>
      <td className="setups-kind">{row.kind ? (SETUP_KIND_LABELS[row.kind] ?? row.kind) : '—'}</td>
      <td className="num">{fmtPx(s?.trigger)}</td>
      <td className="num">{fmtPx(s?.stop)}</td>
      <td className="num" title="Entry (trigger + 1¢) minus the stop, per share">{fmtCents(r)}</td>
      <td className="num" title="Target 1: the leg high or 2R, whichever is higher">{fmtPx(s?.target1)}</td>
      <td className="num setups-distance">{distanceLabel(row) || outcomeLabel(row) || '—'}</td>
      <td><TapeCell row={row} onOpenTrading={onOpenTrading} /></td>
      <td title={catalystTitle(row.pillars)}>{row.grade ?? '—'}</td>
      <td className="num">{row.state === 'triggered' ? fmtR(row.bar_r) : '—'}</td>
      <td className="setups-reason" title={row.reason}>{row.reason}</td>
      <td>
        {row.proposal ? (
          <button
            type="button"
            className="setups-stage"
            onClick={() => stageSetupTicket(row.symbol, stagedLimit(row), onOpenTrading)}
            title={`Stage a BUY limit at ${stagedLimit(row)} on this symbol's ticket. Stop ${fmtPx(s?.stop)}. Nothing is sent until you press Place.`}
          >
            Stage ticket
          </button>
        ) : null}
      </td>
    </SelectableTableRow>
  );
}

export function SetupsBoard({ rows, selectedSymbol, onSelectSymbol, onOpenTrading }: BoardProps) {
  if (rows.length === 0) {
    return (
      <div className="empty-state">
        No setups right now. The scanner watches the HOD Momo names on one-minute bars and lists a
        symbol once it makes a fresh 5% leg.
      </div>
    );
  }
  return (
    <div className="table-wrapper setups-table">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th title="Where the setup is: leg up, armed, near the trigger, triggered, or failed">State</th>
            <th>Setup</th>
            <th title="The last pullback candle's high. Price trading over it is the entry.">Trigger</th>
            <th title="The pullback low">Stop</th>
            <th>Risk</th>
            <th>Target</th>
            <th title="How far under the trigger price is, or how a triggered setup went">Distance</th>
            <th title="The bot's read of the Level 2 and time and sales at the trigger">Tape</th>
            <th title="Five Pillars at the moment it armed: A = all five, B = four, C = three or fewer or unknown. News passes only for a real catalyst since the prior close.">Grade</th>
            <th title="What the backtest's exit rules made of it, in R (gross)">R</th>
            <th>Why</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <SetupBoardRow
              key={row.symbol}
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
