/** One group's rows as the tiles' popover and the sheet show them: a dot for what the row says about
 * a long trade, the label, the value, and below them the detail and where the number comes from. */
import { STATE_WORDS } from './constants';
import type { ReadGroup, ReadRow } from './types';

export function ReadRowItem({ row }: { row: ReadRow }) {
  return (
    <li className={`sr-row sr-row--${row.state}`} data-testid={`stock-read-row-${row.id}`}>
      <span className="sr-dot" aria-label={STATE_WORDS[row.state]} title={STATE_WORDS[row.state]} />
      <span className="sr-row__label">{row.label}</span>
      <span className="sr-row__value">{row.value}</span>
      {(row.detail || row.source) && (
        <span className="sr-row__detail">
          {row.detail}
          {row.detail && row.source ? ' · ' : ''}
          {row.source && <span className="sr-row__source">{row.source}</span>}
        </span>
      )}
    </li>
  );
}

export function GroupHead({ group }: { group: ReadGroup }) {
  return (
    <div className={`sr-group__head sr-group__head--${group.verdict}`}>
      <span className="sr-dot" aria-hidden="true" />
      <span className="sr-group__label">{group.label}</span>
      <span className="sr-group__value">{group.value}</span>
      <span className="sr-group__question">{group.question}</span>
    </div>
  );
}

export function ReadRowList({ rows }: { rows: ReadRow[] }) {
  return (
    <ul className="sr-rows">
      {rows.map(r => <ReadRowItem key={r.id} row={r} />)}
    </ul>
  );
}
