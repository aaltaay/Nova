/**
 * What a row of the phone's Search shows beside the desk's own match (mockup v1, 2026-11-18). Pure.
 *
 * The matching and its order are the desk's (`components/globalBarSearchView`). This file only words a
 * row for a phone: the company name without its share-class tail, and one short line saying where the
 * stock is on the desk right now -- HOD Momo today, a place on a board, the hot list -- or nothing.
 */
import type { SearchOption } from '../components/globalBarSearchView';
import type { MatchSpan } from '../components/tickerSearchSuggestions';

export interface SearchBoard {
  /** The board's name as the Scan tab writes it. */
  name: string;
  /** The board as the scanner serves it, top first. */
  symbols: readonly string[];
}

export interface SearchTagSources {
  /** Symbol to the time of its first HOD Momo alert today, "HH:MM" ET. Empty until the list has been read. */
  hodAt: ReadonlyMap<string, string>;
  boards: readonly SearchBoard[];
  /** Today's hot list. */
  hot: ReadonlySet<string>;
}

export interface PhoneSearchRow {
  symbol: string;
  /** Null for a row that is only what was typed. */
  name: string | null;
  exchange: string | null;
  /** Where the stock is on the desk now; null when it is nowhere. */
  tag: string | null;
  /** The move in percent points as the desk's search knows it; null off the boards. */
  movePct: number | null;
  /** The typed characters inside the symbol, for the highlight. */
  match: MatchSpan | null;
  /** The row is exactly what was typed, not a match: the desk's "open anyway" row. */
  typed: boolean;
}

/**
 * The words a listing ends with that say what kind of share it is, never which company. Longest first,
 * so "Class A Ordinary Shares" goes whole.
 */
const NAME_TAILS: readonly RegExp[] = [
  /\s+American Depositary (Shares|Receipts)\b.*$/i,
  /\s+Class [A-Z]\b.*$/i,
  /\s+(Common|Ordinary) (Stock|Shares)\b.*$/i,
  /\s+ADS$/i,
];

/** "Global Mofy AI Limited Class A Ordinary Shares" reads "Global Mofy AI Limited". An empty result keeps the name. */
export function shortCompanyName(name: string): string {
  let out = name.trim();
  for (const tail of NAME_TAILS) {
    const cut = out.replace(tail, '').replace(/[\s,]+$/, '');
    if (cut) out = cut;
  }
  return out;
}

/** Where a stock is on the desk now, most telling first: HOD Momo today, its place on a board, the hot list. */
export function searchTag(symbol: string, src: SearchTagSources): string | null {
  const at = src.hodAt.get(symbol);
  if (at) return `HOD Momo ${at}`;
  for (const board of src.boards) {
    const place = board.symbols.indexOf(symbol);
    if (place >= 0) return `${board.name} #${place + 1}`;
  }
  return src.hot.has(symbol) ? 'Hot list' : null;
}

export function searchRows(options: readonly SearchOption[], src: SearchTagSources): PhoneSearchRow[] {
  return options.map(({ symbol, suggestion }) => ({
    symbol,
    name: suggestion?.name ? shortCompanyName(suggestion.name) : null,
    exchange: suggestion?.exchange ?? null,
    tag: searchTag(symbol, src),
    movePct: suggestion?.movePct ?? null,
    match: suggestion?.symbolMatch ?? null,
    typed: suggestion == null,
  }));
}

/**
 * Today's hot list as rows of the search, before anything is typed: `symbols` in the list's order, each with
 * the change the list holds for it and the directory's name. A fact neither holds stays null.
 */
export function hotOptions(
  entries: readonly { symbol: string; change_pct: number | null }[],
  symbols: readonly string[],
  directory: { bySymbol: ReadonlyMap<string, { name: string; exchange: string }> } | null,
): SearchOption[] {
  const bySymbol = new Map(entries.map((e) => [e.symbol, e]));
  return symbols.map((symbol) => {
    const change = bySymbol.get(symbol)?.change_pct ?? null;
    const listed = directory?.bySymbol.get(symbol) ?? null;
    return {
      symbol,
      suggestion: {
        symbol,
        source: 'listed' as const,
        // The hot list holds a fraction; the search's rows hold percent points.
        movePct: change == null || !Number.isFinite(change) ? null : change * 100,
        name: listed?.name || null,
        exchange: listed?.exchange || null,
        symbolMatch: null,
        nameMatch: null,
      },
    };
  });
}

/** The line under the matches: how many there are beyond the rows that fit, or the desk's own note. */
export function searchFootText(shown: number, total: number, note: string | null): string {
  if (note) return note;
  if (total > shown) return `${shown} of ${total} matches · keep typing to narrow`;
  return total === 1 ? '1 match' : `${total} matches`;
}
