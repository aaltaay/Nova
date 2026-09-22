/**
 * The centre of the global bar: a compact ticker search on every view.
 * Typing lists, under the input, what the desk already holds that starts
 * with it -- Trader tabs, positions, the scanner tables -- and the first row
 * is exactly what was typed, so Enter opens that (AA never opens AAPL).
 * ↑ ↓ pick another row, Enter or a click opens it in the Trader, Escape
 * closes the list. Enter is handled on the input itself rather than left to
 * implicit form submission. The text is selected after a look-up and again
 * whenever the box takes focus, so the next symbol simply overtypes it.
 */
import { Search } from 'lucide-react';
import { Popover } from 'radix-ui';
import { useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import {
  GLOBAL_BAR_SEARCH_ARIA,
  GLOBAL_BAR_SEARCH_LIST_ARIA,
  GLOBAL_BAR_SEARCH_MAX_SUGGESTIONS,
  GLOBAL_BAR_SEARCH_PLACEHOLDER,
  GLOBAL_BAR_SEARCH_SOURCE_LABELS,
  GLOBAL_BAR_SEARCH_TITLE,
  GLOBAL_BAR_SEARCH_TYPED_HINT,
} from '../constants';
import { useScannerDockRows } from '../scanner/useScannerDockRows';
import { formatSignedPct, pctTone } from '../stock_view/tabContext';
import {
  normalizeTickerQuery,
  tickerSuggestions,
  type TickerSuggestion,
  type TickerSuggestionPools,
} from './tickerSearchSuggestions';
import './globalBarTickerSearch.css';

interface Props {
  onLookup: (symbol: string) => void;
  /** Open Trader tabs, offered first. */
  tabs?: TickerSuggestionPools['tabs'];
  /** Account positions; flat ones are not offered. */
  positions?: TickerSuggestionPools['positions'];
}

type SearchOption = { symbol: string; suggestion: TickerSuggestion | null };

const NO_TABS: TickerSuggestionPools['tabs'] = [];
const NO_POSITIONS: TickerSuggestionPools['positions'] = [];

export function GlobalBarTickerSearch({ onLookup, tabs = NO_TABS, positions = NO_POSITIONS }: Props) {
  const [value, setValue] = useState('');
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const selectOnFocus = useRef(false);
  const listId = useId();
  const rows = useScannerDockRows();
  const query = normalizeTickerQuery(value);

  const options = useMemo<SearchOption[]>(() => {
    if (!query) return [];
    const found = tickerSuggestions(query, { tabs, positions, rows }, GLOBAL_BAR_SEARCH_MAX_SUGGESTIONS);
    const typed = found.some((s) => s.symbol === query) ? [] : [{ symbol: query, suggestion: null }];
    return [...typed, ...found.map((s) => ({ symbol: s.symbol, suggestion: s }))];
  }, [query, tabs, positions, rows]);
  const current = Math.max(0, Math.min(active, options.length - 1));
  const open = focused && !dismissed && options.length > 0;

  function close() {
    setDismissed(true);
    setActive(0);
  }

  function commit(symbol: string | undefined) {
    if (!symbol) return;
    onLookup(symbol);
    setValue(symbol);
    close();
    inputRef.current?.select();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    commit(options[current]?.symbol);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!options.length) return;
      e.preventDefault();
      if (!open) {
        setDismissed(false);
        return;
      }
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setActive(Math.max(0, Math.min(options.length - 1, current + step)));
    } else if (e.key === 'Enter') {
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      commit(options[current]?.symbol);
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault();
        close();
      } else {
        e.currentTarget.blur();
      }
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={(next) => { if (!next) close(); }}>
      <Popover.Anchor asChild>
        <form
          ref={formRef}
          className="global-app-bar__search"
          role="search"
          data-testid="global-bar-search"
          title={GLOBAL_BAR_SEARCH_TITLE}
          onSubmit={submit}
        >
          <Search className="global-app-bar__search-icon" aria-hidden="true" />
          <input
            ref={inputRef}
            className="global-app-bar__search-input"
            type="text"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={open}
            aria-controls={open ? listId : undefined}
            aria-activedescendant={open ? `${listId}-${current}` : undefined}
            value={value}
            onChange={(e) => {
              setValue(e.target.value.toUpperCase());
              setDismissed(false);
              setActive(0);
            }}
            // Focus selects the whole symbol, so a click then typing replaces the
            // last look-up instead of appending to it (MSFT + AAPL opened "MSFTAAPL").
            onFocus={(e) => {
              setFocused(true);
              e.currentTarget.select();
              selectOnFocus.current = true;
            }}
            // The click that focused the box would otherwise drop that selection.
            onMouseUp={(e) => {
              if (selectOnFocus.current) e.preventDefault();
              selectOnFocus.current = false;
            }}
            onBlur={() => {
              setFocused(false);
              selectOnFocus.current = false;
            }}
            onKeyDown={onKeyDown}
            placeholder={GLOBAL_BAR_SEARCH_PLACEHOLDER}
            aria-label={GLOBAL_BAR_SEARCH_ARIA}
            autoComplete="off"
            spellCheck={false}
            enterKeyHint="go"
            data-testid="global-bar-search-input"
          />
        </form>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          className="global-bar-search-list"
          side="bottom"
          align="start"
          sideOffset={4}
          collisionPadding={8}
          data-testid="global-bar-search-list"
          // Focus stays in the input: the list is read with ↑ ↓, not tabbed into.
          onOpenAutoFocus={(e) => e.preventDefault()}
          onCloseAutoFocus={(e) => e.preventDefault()}
          onInteractOutside={(e) => {
            if (formRef.current?.contains(e.target as Node)) e.preventDefault();
          }}
        >
          <ul id={listId} role="listbox" aria-label={GLOBAL_BAR_SEARCH_LIST_ARIA}>
            {options.map((option, i) => {
              const move = option.suggestion ? formatSignedPct(option.suggestion.movePct) : '';
              return (
                <li
                  key={option.symbol}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === current}
                  className={`global-bar-search-list__row${i === current ? ' is-active' : ''}`}
                  data-testid={`global-bar-search-option-${option.symbol}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => commit(option.symbol)}
                >
                  <span className="global-bar-search-list__symbol">{option.symbol}</span>
                  <span className="global-bar-search-list__source">
                    {option.suggestion
                      ? GLOBAL_BAR_SEARCH_SOURCE_LABELS[option.suggestion.source]
                      : GLOBAL_BAR_SEARCH_TYPED_HINT}
                  </span>
                  {move && (
                    <span
                      className={`global-bar-search-list__move global-bar-search-list__move--${pctTone(option.suggestion?.movePct)}`}
                    >
                      {move}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
