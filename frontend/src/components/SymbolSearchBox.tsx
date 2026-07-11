/** Header symbol lookup — opens the ticker detail page without a side panel. */
import { useState } from 'react';

interface Props {
  onLookup: (symbol: string) => void;
}

export function SymbolSearchBox({ onLookup }: Props) {
  const [input, setInput] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    if (sym) onLookup(sym);
  }

  return (
    <form className="header-symbol-search" onSubmit={handleSubmit}>
      <input
        className="side-search-input header-symbol-input"
        type="text"
        value={input}
        onChange={e => setInput(e.target.value.toUpperCase())}
        placeholder="Symbol"
        autoComplete="off"
        spellCheck={false}
        aria-label="Look up symbol"
      />
      <button type="submit" className="side-search-btn">Look Up</button>
    </form>
  );
}
