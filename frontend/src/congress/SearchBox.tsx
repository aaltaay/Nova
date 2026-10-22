/**
 * "Member or ticker" (ADR 066): a member's name (or seat) opens their page; a ticker opens who traded it. The list
 * under the box shows the matches as you type; Enter takes the first. It also narrows the Members list.
 */
import { useMemo, useState } from 'react';
import { Face } from './Face';
import { seat } from './format';
import type { Member } from './types';

const TICKER = /^[A-Za-z][A-Za-z0-9.-]{0,9}$/;

export function SearchBox({ query, onQuery, members, onMember, onTicker }: {
  query: string;
  onQuery: (q: string) => void;
  members: Map<string, Member>;
  onMember: (bioguide: string) => void;
  onTicker: (ticker: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const q = query.trim();
  const found = useMemo(() => {
    if (q.length < 2) return [];
    const low = q.toLowerCase();
    return [...members.values()]
      .filter((m) => m.name.toLowerCase().includes(low) || seat(m).toLowerCase() === low)
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, 6);
  }, [q, members]);
  const ticker = TICKER.test(q) && q.length <= 6 ? q.toUpperCase() : null;
  const choose = (pick: () => void) => {
    pick();
    setOpen(false);
  };
  return (
    <div className="cg-search">
      <input
        type="search"
        placeholder="Member or ticker"
        value={query}
        onChange={(e) => { onQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter') return;
          if (found.length) choose(() => onMember(found[0].bioguide));
          else if (ticker) choose(() => onTicker(ticker));
        }}
        aria-label="Search members or tickers"
        data-testid="congress-search"
      />
      {open && (found.length || ticker) ? (
        <div className="cg-search__list" role="listbox">
          {found.map((m) => (
            <button key={m.bioguide} type="button" role="option" aria-selected={false}
              onMouseDown={(e) => e.preventDefault()} onClick={() => choose(() => onMember(m.bioguide))}>
              <Face member={m} size={22} /> <span>{m.name}</span> <span className="cg-muted">{seat(m)}</span>
            </button>
          ))}
          {ticker ? (
            <button type="button" role="option" aria-selected={false} onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(() => onTicker(ticker))} data-testid="congress-search-ticker">
              <span className="cg-tile">{ticker.slice(0, 5)}</span> <span>Who traded {ticker}</span>
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
