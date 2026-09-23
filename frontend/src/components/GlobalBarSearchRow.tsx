/**
 * One row of the bar search's list: symbol and company name (matched part
 * marked), where the desk knows it from, the listing exchange, and the move.
 */
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import {
  GLOBAL_BAR_SEARCH_REMOVE_RECENT_ARIA,
  GLOBAL_BAR_SEARCH_SOURCE_LABELS,
} from '../constants';
import { formatSignedPct, pctTone } from '../stock_view/tabContext';
import type { SearchOption } from './globalBarSearchView';
import type { MatchSpan } from './tickerSearchSuggestions';

function marked(text: string, span: MatchSpan | null): ReactNode {
  if (!span || span[1] <= span[0] || span[0] >= text.length) return text;
  const [start, end] = [span[0], Math.min(span[1], text.length)];
  return (
    <>
      {text.slice(0, start)}
      <mark className="global-bar-search-list__mark">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
}

interface Props {
  id: string;
  option: SearchOption;
  active: boolean;
  typedHint: string;
  onPick: () => void;
  onHover: () => void;
  /** Recent rows can be forgotten from the list. */
  onForget?: () => void;
}

export function GlobalBarSearchRow({ id, option, active, typedHint, onPick, onHover, onForget }: Props) {
  const s = option.suggestion;
  const move = s ? formatSignedPct(s.movePct) : '';
  const source = s ? (s.source === 'listed' ? '' : GLOBAL_BAR_SEARCH_SOURCE_LABELS[s.source]) : typedHint;
  return (
    <li
      id={id}
      role="option"
      aria-selected={active}
      className={`global-bar-search-list__row${active ? ' is-active' : ''}${s ? '' : ' is-typed'}`}
      data-testid={`global-bar-search-option-${option.symbol}`}
      onMouseDown={(e) => e.preventDefault()}
      onMouseEnter={onHover}
      onClick={onPick}
    >
      <span className="global-bar-search-list__symbol">{marked(option.symbol, s?.symbolMatch ?? null)}</span>
      <span className="global-bar-search-list__name" title={s?.name ?? undefined}>
        {s?.name ? marked(s.name, s.nameMatch) : source}
      </span>
      {s?.name && source && <span className="global-bar-search-list__source">{source}</span>}
      {s?.exchange && <span className="global-bar-search-list__exchange">{s.exchange}</span>}
      {move && (
        <span className={`global-bar-search-list__move global-bar-search-list__move--${pctTone(s?.movePct)}`}>
          {move}
        </span>
      )}
      {onForget && (
        <button
          type="button"
          className="global-bar-search-list__forget"
          aria-label={GLOBAL_BAR_SEARCH_REMOVE_RECENT_ARIA(option.symbol)}
          title={GLOBAL_BAR_SEARCH_REMOVE_RECENT_ARIA(option.symbol)}
          tabIndex={-1}
          data-testid={`global-bar-search-forget-${option.symbol}`}
          onClick={(e) => {
            e.stopPropagation();
            onForget();
          }}
        >
          <X aria-hidden="true" />
        </button>
      )}
    </li>
  );
}
