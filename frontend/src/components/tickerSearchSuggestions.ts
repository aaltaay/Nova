/**
 * What the bar's ticker search offers under the input. Pure.
 *
 * Desk symbols come first, in the desk's order -- open Trader tabs,
 * positions, recent look-ups, then the scanner tables and catalysts -- and
 * then every listed symbol from the directory (symbolDirectory.ts), ranked:
 * exact symbol, symbol prefix (shortest first), company name starting with
 * the text, then a later word of the name. A regex / wildcard query
 * (tickerSearchQuery.ts) matches symbols only.
 *
 * It never offers a symbol that is neither on the desk nor listed, and a move
 * the desk does not know stays null.
 */
import { GLOBAL_BAR_SEARCH_NAME_MIN_CHARS } from '../constantGroups/global_bar';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import { tabContextFor } from '../stock_view/tabContext';
import type { SymbolDirectory } from './symbolDirectory';
import { parseTickerQuery, type TickerQuery } from './tickerSearchQuery';

export type TickerSuggestionSource =
  | 'tab'
  | 'position'
  | 'recent'
  | 'gappers'
  | 'gainers'
  | 'losers'
  | 'afterhours'
  | 'catalysts'
  | 'listed';

/** `[start, end)` of the matched characters, for highlighting. */
export type MatchSpan = readonly [number, number];

export interface TickerSuggestion {
  symbol: string;
  source: TickerSuggestionSource;
  /** Signed move in percent points, as the Trader tab prints it; null when unknown. */
  movePct: number | null;
  /** Company name and listing exchange from the directory; null when not loaded / not listed. */
  name: string | null;
  exchange: string | null;
  symbolMatch: MatchSpan | null;
  nameMatch: MatchSpan | null;
}

export interface TickerSuggestionPools {
  tabs: readonly string[];
  positions: readonly { symbol: string; qty: number }[];
  rows: ScannerDockRows | null;
  recents?: readonly string[];
  directory?: SymbolDirectory | null;
}

export interface TickerSearchResult {
  suggestions: TickerSuggestion[];
  /** Every match, before the limit. */
  total: number;
}

export function normalizeTickerQuery(raw: string): string {
  return raw.trim().toUpperCase();
}

type Match = { symbolMatch: MatchSpan | null; nameMatch: MatchSpan | null; rank: number };
type Matcher = (symbol: string, nameUpper: string | null) => Match | null;

const NAME_BOUNDARY = '[^A-Z0-9]';

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function textMatcher(text: string): Matcher {
  const words = text.split(' ').filter(Boolean).map(escapeRegex);
  const nameRe = text.replace(/ /g, '').length >= GLOBAL_BAR_SEARCH_NAME_MIN_CHARS && words.length
    ? new RegExp(`(^|${NAME_BOUNDARY})(${words.join(`${NAME_BOUNDARY}+`)})`)
    : null;
  return (symbol, nameUpper) => {
    const symbolMatch: MatchSpan | null = symbol.startsWith(text) ? [0, text.length] : null;
    let nameMatch: MatchSpan | null = null;
    if (nameRe && nameUpper) {
      const m = nameRe.exec(nameUpper);
      if (m) {
        const start = m.index + m[1].length;
        nameMatch = [start, start + m[2].length];
      }
    }
    if (!symbolMatch && !nameMatch) return null;
    const rank = symbol === text ? 0 : symbolMatch ? 1 : nameMatch && nameMatch[0] === 0 ? 2 : 3;
    return { symbolMatch, nameMatch, rank };
  };
}

function patternMatcher(regex: RegExp): Matcher {
  return (symbol) => {
    const m = regex.exec(symbol);
    return m ? { symbolMatch: [m.index, m.index + m[0].length], nameMatch: null, rank: 1 } : null;
  };
}

export function searchTickers(
  query: TickerQuery,
  { tabs, positions, rows, recents = [], directory = null }: TickerSuggestionPools,
  limit: number,
): TickerSearchResult {
  let matcher: Matcher;
  if (query.kind === 'text') matcher = textMatcher(query.text);
  else if (query.kind === 'pattern') matcher = patternMatcher(query.regex);
  else return { suggestions: [], total: 0 };

  const seen = new Set<string>();
  const desk: (TickerSuggestion & { rank: number })[] = [];
  const offer = (raw: string, source: TickerSuggestionSource) => {
    const symbol = normalizeTickerQuery(raw);
    if (!symbol || seen.has(symbol)) return;
    const listed = directory?.bySymbol.get(symbol) ?? null;
    const match = matcher(symbol, listed?.nameUpper ?? null);
    if (!match) return;
    seen.add(symbol);
    desk.push({
      symbol,
      source,
      movePct: tabContextFor(symbol, rows).gapPct,
      name: listed?.name || null,
      exchange: listed?.exchange || null,
      ...match,
    });
  };
  tabs.forEach((symbol) => offer(symbol, 'tab'));
  positions.forEach((p) => { if (p.qty !== 0) offer(p.symbol, 'position'); });
  recents.forEach((symbol) => offer(symbol, 'recent'));
  if (rows) {
    rows.gappers.forEach((r) => offer(r.symbol, 'gappers'));
    rows.gainers.forEach((r) => offer(r.symbol, 'gainers'));
    rows.losers.forEach((r) => offer(r.symbol, 'losers'));
    rows.afterhours.forEach((r) => offer(r.symbol, 'afterhours'));
    rows.catalysts.forEach((r) => offer(r.symbol, 'catalysts'));
  }

  const listed: (TickerSuggestion & { rank: number })[] = [];
  for (const entry of directory?.entries ?? []) {
    if (seen.has(entry.symbol)) continue;
    const match = matcher(entry.symbol, entry.nameUpper);
    if (!match) continue;
    listed.push({
      symbol: entry.symbol,
      source: 'listed',
      movePct: null,
      name: entry.name || null,
      exchange: entry.exchange || null,
      ...match,
    });
  }
  listed.sort((a, b) => a.rank - b.rank
    || (a.rank <= 1 ? a.symbol.length - b.symbol.length : 0)
    || a.symbol.localeCompare(b.symbol));

  // The exact symbol leads; otherwise the desk's own order, then the listing.
  const all = [...desk, ...listed];
  const exact = all.findIndex((s) => s.rank === 0);
  if (exact > 0) all.unshift(...all.splice(exact, 1));
  const suggestions = all.slice(0, limit).map(({ rank: _rank, ...s }) => s);
  return { suggestions, total: all.length };
}

/** searchTickers for a raw string; a regex / wildcard / invalid query offers nothing here. */
export function tickerSuggestions(query: string, pools: TickerSuggestionPools, limit: number): TickerSuggestion[] {
  const parsed = parseTickerQuery(query);
  if (parsed.kind !== 'text') return [];
  return searchTickers(parsed, pools, limit).suggestions;
}
