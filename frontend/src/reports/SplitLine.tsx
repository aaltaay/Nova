/** Yours and the bots' beside a Reports total (ADR 069, mockup reports-v1): each book's dot and figure. */
import { REPORTS_SPLIT_BOTS, REPORTS_SPLIT_YOU } from './booksConstants';
import type { FigureSplit, SplitFigure } from './reportsView';

interface Props {
  split: FigureSplit | null;
  /** One book per line (the R-multiple and drawdown cards) instead of side by side. */
  stacked?: boolean;
}

const tone = (figure: SplitFigure | null): string =>
  figure?.value == null ? '' : figure.value > 0 ? ' pnl-pos' : figure.value < 0 ? ' pnl-neg' : '';

function Part({ book, label, figure }: { book: 'you' | 'bots'; label: string; figure: SplitFigure | null }) {
  return (
    <span className={`reports-split__part${tone(figure)}`} title={label} data-testid={`reports-split-${book}`}>
      <i className={`reports-split__dot is-${book}`} aria-hidden />
      <span className="reports-split__sr">{label}: </span>
      {figure?.text ?? '—'}
    </span>
  );
}

export function SplitLine({ split, stacked = false }: Props) {
  if (!split) return null;
  return (
    <span className={`reports-split${stacked ? ' is-stacked' : ''}`} data-testid="reports-split">
      <Part book="you" label={REPORTS_SPLIT_YOU} figure={split.you} />
      <Part book="bots" label={REPORTS_SPLIT_BOTS} figure={split.bots} />
    </span>
  );
}
