/**
 * What the bar search's list shows for a query. Pure.
 *
 * - Nothing typed (or the box just focused): the recent symbols.
 * - Text: exactly what was typed first when it could be a ticker -- Enter's
 *   default, so AA never opens AAPL -- then desk and listed matches. When the
 *   directory is loaded, does not list the text, and only company names
 *   match (APPLE -> AAPL), the first match is the default instead.
 * - Regex / wildcard: the matches, with the full count in the footer.
 */
import {
  GLOBAL_BAR_SEARCH_DIRECTORY_LOADING,
  GLOBAL_BAR_SEARCH_MAX_PATTERN_SUGGESTIONS,
  GLOBAL_BAR_SEARCH_MAX_SUGGESTIONS,
  GLOBAL_BAR_SEARCH_NO_MATCH,
  GLOBAL_BAR_SEARCH_TIPS,
  GLOBAL_BAR_SEARCH_TYPED_HINT,
  GLOBAL_BAR_SEARCH_TYPED_UNLISTED_HINT,
  globalBarSearchDirectoryUnavailable,
  globalBarSearchPatternSummary,
} from '../constantGroups/global_bar';
import { tabContextFor } from '../stock_view/tabContext';
import type { SymbolDirectoryState } from './symbolDirectory';
import { looksLikeSymbol, type TickerQuery } from './tickerSearchQuery';
import { searchTickers, type TickerSuggestion, type TickerSuggestionPools } from './tickerSearchSuggestions';

export type SearchOption = { symbol: string; suggestion: TickerSuggestion | null };

export interface SearchFooter {
  text: string;
  tone: 'muted' | 'warn';
}

export interface SearchView {
  options: SearchOption[];
  defaultIndex: number;
  typedHint: string;
  /** The list is the recent symbols (heading shown, rows forgettable). */
  recentMode: boolean;
  footer: SearchFooter | null;
}

function directoryNote(dir: Pick<SymbolDirectoryState, 'status' | 'error' | 'directory'>): SearchFooter | null {
  if (dir.directory) return null;
  if (dir.status === 'error') return { text: globalBarSearchDirectoryUnavailable(dir.error), tone: 'muted' };
  if (dir.status === 'loading') return { text: GLOBAL_BAR_SEARCH_DIRECTORY_LOADING, tone: 'muted' };
  return null;
}

export function searchView(
  query: TickerQuery,
  pools: TickerSuggestionPools,
  dir: Pick<SymbolDirectoryState, 'status' | 'error' | 'directory'>,
): SearchView {
  const base: SearchView = { options: [], defaultIndex: 0, typedHint: GLOBAL_BAR_SEARCH_TYPED_HINT, recentMode: false, footer: null };

  if (query.kind === 'empty') {
    const options = (pools.recents ?? []).slice(0, GLOBAL_BAR_SEARCH_MAX_SUGGESTIONS).map((symbol) => {
      const listed = dir.directory?.bySymbol.get(symbol) ?? null;
      return {
        symbol,
        suggestion: {
          symbol,
          source: 'recent' as const,
          movePct: tabContextFor(symbol, pools.rows).gapPct,
          name: listed?.name || null,
          exchange: listed?.exchange || null,
          symbolMatch: null,
          nameMatch: null,
        },
      };
    });
    return { ...base, options, recentMode: true, footer: options.length ? { text: GLOBAL_BAR_SEARCH_TIPS, tone: 'muted' } : null };
  }

  if (query.kind === 'invalid') return { ...base, footer: { text: query.message, tone: 'warn' } };

  const note = directoryNote(dir);
  if (query.kind === 'pattern') {
    const limit = GLOBAL_BAR_SEARCH_MAX_PATTERN_SUGGESTIONS;
    const { suggestions, total } = searchTickers(query, pools, limit);
    const summary = globalBarSearchPatternSummary(total, suggestions.length, query.flavor);
    return {
      ...base,
      options: suggestions.map((s) => ({ symbol: s.symbol, suggestion: s })),
      footer: { text: note ? `${summary} · ${note.text}` : summary, tone: total ? 'muted' : 'warn' },
    };
  }

  const text = query.text;
  const { suggestions } = searchTickers(query, pools, GLOBAL_BAR_SEARCH_MAX_SUGGESTIONS);
  const typed = looksLikeSymbol(text) && !suggestions.some((s) => s.symbol === text);
  const options: SearchOption[] = [
    ...(typed ? [{ symbol: text, suggestion: null }] : []),
    ...suggestions.map((s) => ({ symbol: s.symbol, suggestion: s })),
  ];
  const unlisted = dir.directory != null && !dir.directory.bySymbol.has(text);
  const namesOnly = suggestions.length > 0 && suggestions.every((s) => !s.symbolMatch);
  return {
    ...base,
    options,
    typedHint: typed && unlisted ? GLOBAL_BAR_SEARCH_TYPED_UNLISTED_HINT : GLOBAL_BAR_SEARCH_TYPED_HINT,
    defaultIndex: typed && unlisted && namesOnly ? 1 : 0,
    footer: note ?? (options.length ? null : { text: GLOBAL_BAR_SEARCH_NO_MATCH, tone: 'warn' }),
  };
}
