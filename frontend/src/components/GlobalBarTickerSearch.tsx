/**
 * The centre of the global bar: the ticker search on every view.
 *
 * Focus shows the recent symbols. Typing searches the desk -- Trader tabs,
 * positions, recents, the scanner tables -- and then every listed symbol by
 * ticker or company name (symbolDirectory.ts, loaded on first focus).
 * `/regex/` and `A*X` wildcards filter every listed symbol
 * (tickerSearchQuery.ts). What the list shows: globalBarSearchView.ts.
 *
 * The first row is exactly what was typed when it could be a ticker, so
 * Enter opens that (AA never opens AAPL). ↑ ↓ pick another row, Tab completes
 * the picked symbol into the box, Enter or a click opens it in the Trader,
 * Shift+Delete forgets a recent symbol, Escape closes the list. The text is
 * selected after a look-up and again whenever the box takes focus, so the
 * next symbol simply overtypes it.
 */
import { Search } from 'lucide-react';
import { Popover } from 'radix-ui';
import { useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import {
  GLOBAL_BAR_SEARCH_ARIA,
  GLOBAL_BAR_SEARCH_LIST_ARIA,
  GLOBAL_BAR_SEARCH_PLACEHOLDER,
  GLOBAL_BAR_SEARCH_RECENTS_HEADING,
  GLOBAL_BAR_SEARCH_TITLE,
} from '../constants';
import { useScannerDockRows } from '../scanner/useScannerDockRows';
import { GlobalBarSearchRow } from './GlobalBarSearchRow';
import { searchView } from './globalBarSearchView';
import { useSymbolDirectory } from './symbolDirectory';
import { isRegexInput, parseTickerQuery } from './tickerSearchQuery';
import { useTickerRecents } from './tickerSearchRecents';
import type { TickerSuggestionPools } from './tickerSearchSuggestions';
import './globalBarTickerSearch.css';

interface Props {
  onLookup: (symbol: string) => void;
  /** Open Trader tabs, offered first. */
  tabs?: TickerSuggestionPools['tabs'];
  /** Account positions; flat ones are not offered. */
  positions?: TickerSuggestionPools['positions'];
}

const NO_TABS: TickerSuggestionPools['tabs'] = [];
const NO_POSITIONS: TickerSuggestionPools['positions'] = [];
const EMPTY_QUERY = parseTickerQuery('');

export function GlobalBarTickerSearch({ onLookup, tabs = NO_TABS, positions = NO_POSITIONS }: Props) {
  const [value, setValue] = useState('');
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  /** Just focused, nothing typed yet: the list is the recents, whatever the box holds. */
  const [browsing, setBrowsing] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [wantDirectory, setWantDirectory] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const selectOnFocus = useRef(false);
  const listId = useId();
  const rows = useScannerDockRows();
  const directory = useSymbolDirectory(wantDirectory);
  const { recents, remember, forget } = useTickerRecents(tabs);
  const query = useMemo(() => (browsing ? EMPTY_QUERY : parseTickerQuery(value)), [browsing, value]);

  const view = useMemo(
    () => searchView(query, { tabs, positions, rows, recents, directory: directory.directory }, directory),
    [query, tabs, positions, rows, recents, directory],
  );
  const { options } = view;
  const current = Math.max(0, Math.min(active ?? view.defaultIndex, options.length - 1));
  const open = focused && !dismissed && (options.length > 0 || view.footer != null);

  function close() {
    setDismissed(true);
    setActive(null);
  }

  function commit(symbol: string | undefined) {
    if (!symbol) return;
    onLookup(symbol);
    remember(symbol);
    setValue(symbol);
    setBrowsing(false);
    close();
    inputRef.current?.select();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    commit(options[current]?.symbol);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    const option = options[current];
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
      commit(option?.symbol);
    } else if (e.key === 'Tab' && !e.shiftKey && open && option?.suggestion && option.symbol !== value) {
      e.preventDefault();
      setValue(option.symbol);
      setBrowsing(false);
      setActive(null);
    } else if (e.key === 'Delete' && e.shiftKey && open && option?.suggestion?.source === 'recent') {
      e.preventDefault();
      forget(option.symbol);
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
            aria-activedescendant={open && options.length ? `${listId}-${current}` : undefined}
            value={value}
            onChange={(e) => {
              const raw = e.target.value;
              // A regex keeps its case (\d is not \D); everything else is a ticker or a name.
              setValue(isRegexInput(raw) ? raw : raw.toUpperCase());
              setBrowsing(false);
              setDismissed(false);
              setActive(null);
            }}
            // Focus selects the whole symbol, so a click then typing replaces the
            // last look-up instead of appending to it (MSFT + AAPL opened "MSFTAAPL").
            onFocus={(e) => {
              setFocused(true);
              setBrowsing(true);
              setDismissed(false);
              setActive(null);
              setWantDirectory(true);
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
          {view.recentMode && options.length > 0 && (
            <div className="global-bar-search-list__heading" aria-hidden="true">
              {GLOBAL_BAR_SEARCH_RECENTS_HEADING}
            </div>
          )}
          {options.length > 0 && (
            <ul id={listId} role="listbox" aria-label={GLOBAL_BAR_SEARCH_LIST_ARIA}>
              {options.map((option, i) => (
                <GlobalBarSearchRow
                  key={option.symbol}
                  id={`${listId}-${i}`}
                  option={option}
                  active={i === current}
                  typedHint={view.typedHint}
                  onPick={() => commit(option.symbol)}
                  onHover={() => setActive(i)}
                  onForget={option.suggestion?.source === 'recent' ? () => forget(option.symbol) : undefined}
                />
              ))}
            </ul>
          )}
          {view.footer && (
            <div
              className={`global-bar-search-list__footer global-bar-search-list__footer--${view.footer.tone}`}
              aria-live="polite"
              data-testid="global-bar-search-footer"
            >
              {view.footer.text}
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
