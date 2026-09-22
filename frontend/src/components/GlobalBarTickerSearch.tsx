/**
 * The centre of the global bar: a compact ticker search on every view.
 * Enter opens the symbol in the Trader (the host's lookup); no separate
 * Look Up button. The text stays selected afterwards so the next symbol
 * simply overtypes it.
 */
import { Search } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';
import {
  GLOBAL_BAR_SEARCH_ARIA,
  GLOBAL_BAR_SEARCH_PLACEHOLDER,
  GLOBAL_BAR_SEARCH_TITLE,
} from '../constants';

interface Props {
  onLookup: (symbol: string) => void;
}

export function GlobalBarTickerSearch({ onLookup }: Props) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const sym = value.trim().toUpperCase();
    if (!sym) return;
    onLookup(sym);
    setValue(sym);
    inputRef.current?.select();
  }

  return (
    <form
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
        value={value}
        onChange={(e) => setValue(e.target.value.toUpperCase())}
        onKeyDown={(e) => {
          if (e.key === 'Escape') e.currentTarget.blur();
        }}
        placeholder={GLOBAL_BAR_SEARCH_PLACEHOLDER}
        aria-label={GLOBAL_BAR_SEARCH_ARIA}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="go"
        data-testid="global-bar-search-input"
      />
    </form>
  );
}
