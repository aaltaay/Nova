/**
 * A setup card's own small scanner (ADR 031): the names nearest their trigger,
 * straight from the setup's lane on the live board -- state in the setup's own
 * words, trigger, last, to go, the tape and the grade -- and every cell explains
 * itself on hover (ux/hoverTip.ts). A row opens the symbol in the Trader;
 * right-click is the symbol menu. Nothing here places an order.
 */
import type { MouseEvent } from 'react';
import { BOTS_SCANNER_MAX_ROWS } from '../constantGroups/bots_page';
import { SETUP_COL_TIPS, SETUP_STATUS_TIPS } from '../constantGroups/setups';
import {
  gradeWords,
  isActionable,
  lastWords,
  otherSetups,
  rowRank,
  setupLabel,
  setupShort,
  stateWords,
  tapeRank,
  tapeWords,
  toGoWords,
  triggerWords,
  type SetupRow,
} from '../setups';
import { SortTh, useTableSort, type SortColumns, type TableSort } from '../table_sort';
import { tipProps } from '../ux/hoverTip';
import { openBotSymbolMenu } from './botSymbolMenuStore';

interface Props {
  setup: string;
  rows: readonly SetupRow[];
  /** Every setup's rows, for the tag naming a symbol's other setups. */
  allRows: readonly SetupRow[];
  connected: boolean;
  onOpenSymbol: (symbol: string) => void;
  /** Hovering a symbol highlights it in every card that holds it. */
  hovered: string | null;
  onHover: (symbol: string | null) => void;
  /** What an empty card says instead of "right now" (a recorded moment in Sim names it). */
  emptyText?: string | null;
}

/** What each header sorts on (the whole lane, before the card keeps its top rows). */
const COLUMNS: SortColumns<SetupRow> = {
  symbol: r => r.symbol,
  // The most advanced first: near, armed, triggered, ... (rowRank is lowest-first).
  state: r => -rowRank(r),
  trigger: r => r.setup?.trigger,
  last: r => r.last_price,
  // Nearest the trigger first; a triggered row shows how it went, not a distance.
  to_go: { value: r => (isActionable(r) && r.setup ? r.distance : null), first: 'asc' },
  tape: tapeRank,
  grade: r => r.grade,
};

function Head({ k, label, num = false, sort, onSort }: {
  k: keyof typeof SETUP_COL_TIPS;
  label: string;
  num?: boolean;
  sort: TableSort | null;
  onSort: (key: string) => void;
}) {
  return (
    <SortTh col={k} sort={sort} onSort={onSort} className={num ? 'num' : undefined} {...tipProps(SETUP_COL_TIPS[k], label)}>
      {label}
    </SortTh>
  );
}

export function BotSetupScanner({ setup, rows, allRows, connected, onOpenSymbol, hovered, onHover, emptyText }: Props) {
  const { rows: sorted, sort, onSort } = useTableSort(`bot.scanner.${setup}`, rows, COLUMNS);
  if (!connected) {
    return <p className="bots-scan__empty" {...tipProps(SETUP_STATUS_TIPS.disconnected)}>Scanner not connected.</p>;
  }
  if (rows.length === 0) {
    return (
      <p className="bots-scan__empty" data-testid={`bots-scan-empty-${setup}`} {...tipProps(SETUP_STATUS_TIPS.idle)}>
        {emptyText ?? 'Nothing forming right now.'}
      </p>
    );
  }
  const shown = sorted.slice(0, BOTS_SCANNER_MAX_ROWS);
  const menu = (e: MouseEvent, symbol: string) => {
    e.preventDefault();
    openBotSymbolMenu(symbol, e.clientX, e.clientY);
  };
  return (
    <table className="bots-scan" data-testid={`bots-scan-${setup}`}>
      <thead>
        <tr>
          <Head k="symbol" label="Symbol" sort={sort} onSort={onSort} />
          <Head k="state" label="State" sort={sort} onSort={onSort} />
          <Head k="trigger" label="Trigger" num sort={sort} onSort={onSort} />
          <Head k="last" label="Last" num sort={sort} onSort={onSort} />
          <Head k="to_go" label="To go" num sort={sort} onSort={onSort} />
          <Head k="tape" label="Tape" sort={sort} onSort={onSort} />
          <Head k="grade" label="Gr" sort={sort} onSort={onSort} />
        </tr>
      </thead>
      <tbody>
        {shown.map(row => {
          const state = stateWords(row);
          const trig = triggerWords(row);
          const last = lastWords(row);
          const toGo = toGoWords(row);
          const tape = tapeWords(row);
          const grade = gradeWords(row);
          const others = otherSetups(row, allRows);
          const broke = row.state === 'near' && Boolean(row.setup?.detail?.broke_at);
          return (
            <tr
              key={`${row.symbol}-${row.state}`}
              className={`bots-scan__row bots-scan__row--${row.state}${hovered === row.symbol ? ' is-hot' : ''}`}
              data-testid={`bots-scan-row-${setup}-${row.symbol}`}
              onClick={() => onOpenSymbol(row.symbol)}
              onContextMenu={e => menu(e, row.symbol)}
              onPointerEnter={() => onHover(row.symbol)}
              onPointerLeave={() => onHover(null)}
            >
              <td className="bots-scan__sym">
                <b>{row.symbol}</b>
                {row.proposal ? (
                  <span className="bots-scan__proposed"
                    {...tipProps('This setup raised a proposal: near the trigger with the tape at GO. It is in the inbox; you press Place.', 'Proposed')}>
                    proposed
                  </span>
                ) : null}
                {others.map(o => (
                  <span key={o} className="bots-scan__also"
                    {...tipProps(`${row.symbol} is also on the ${setupLabel(o)} scanner right now. Each setup scores it on its own.`, 'In two setups')}>
                    + {setupShort(o).toLowerCase()}
                  </span>
                ))}
              </td>
              <td>
                <span className={`bots-state bots-state--${broke ? 'broke' : row.state}`}
                  data-testid={`bots-scan-state-${setup}-${row.symbol}`} {...tipProps(state.tip, state.title)}>
                  {state.text}
                </span>
              </td>
              <td className="num" {...tipProps(trig.tip, trig.title)}>{trig.text}</td>
              <td className="num" {...tipProps(last.tip, last.title)}>{last.text}</td>
              <td className={`num${row.state === 'triggered' && (row.bar_r ?? 0) > 0 ? ' is-up' : ''}`}
                {...tipProps(toGo.tip, toGo.title)}>{toGo.text}</td>
              <td>
                {tape ? (
                  <span className={`bots-vbadge bots-vbadge--${row.tape?.verdict ?? 'none'}`}
                    data-testid={`bots-scan-tape-${setup}-${row.symbol}`} {...tipProps(tape.tip, tape.title)}>
                    {tape.text}
                  </span>
                ) : <span className="bots-scan__dot">·</span>}
              </td>
              <td {...tipProps(grade.tip, grade.title)}>{grade.text}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
