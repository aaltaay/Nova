/**
 * The four books beside a Reports total (ADR 072, mockup three-books v1 "Account › Reports"): each book's dot, in its
 * colour, and its figure, in the books' order. A total lists all four; a day passes only the books that traded it.
 */
import { OWNERS, OWNER_COLORS, OWNER_NAMES, type Owner } from '../constantGroups/owners';
import type { FigureSplit, SplitFigure } from './reportsView';

interface Props {
  split: FigureSplit | null;
  /** The books drawn, in order: every book by default. */
  books?: readonly Owner[];
  /** One book per line (the R-multiple and drawdown cards) instead of side by side. */
  stacked?: boolean;
}

const tone = (figure: SplitFigure | null): string =>
  figure?.value == null ? '' : figure.value > 0 ? ' pnl-pos' : figure.value < 0 ? ' pnl-neg' : '';

function Part({ book, figure }: { book: Owner; figure: SplitFigure | null }) {
  const label = OWNER_NAMES[book];
  return (
    <span className={`reports-split__part${tone(figure)}`} title={label} data-testid={`reports-split-${book}`}>
      <i className={`reports-split__dot is-${book}`} style={{ background: OWNER_COLORS[book] }} aria-hidden />
      <span className="reports-split__sr">{label}: </span>
      {figure?.text ?? '—'}
    </span>
  );
}

export function SplitLine({ split, books = OWNERS, stacked = false }: Props) {
  if (!split || books.length === 0) return null;
  return (
    <span className={`reports-split${stacked ? ' is-stacked' : ''}`} data-testid="reports-split">
      {books.map((book) => <Part key={book} book={book} figure={split[book]} />)}
    </span>
  );
}
