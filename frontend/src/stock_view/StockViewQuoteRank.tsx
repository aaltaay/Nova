/**
 * The symbol's place on each scanner list, beside the ticker in the Trader's
 * quote head ("#1 Gappers", "#4 Gainers"). Its own leaf so a scanner price
 * patch redraws these chips and nothing else. Rules: `quoteRank.ts`.
 */
import { memo, useMemo } from 'react';
import { useLiveScannerFeedOptional } from '../scanner';
import { tipProps } from '../ux/hoverTip';
import { rankTip, symbolRanks } from './quoteRank';

/** Ranks at or above this read as a leader (accent colour). */
const RANK_LEADER_MAX = 3;

/** Memoized: the quote head renders on every print; the ranks change with the scanner, not with it (#707). */
export const StockViewQuoteRank = memo(function StockViewQuoteRank({ symbol }: { symbol: string }) {
  const feed = useLiveScannerFeedOptional();
  const ranks = useMemo(() => symbolRanks(symbol, feed), [symbol, feed]);

  if (ranks.state === 'unknown') {
    return (
      <span
        className="sv-quote-rank sv-quote-rank--none"
        data-testid="stock-view-quote-rank"
        {...tipProps(ranks.why, 'Rank unknown')}
      >
        #?
      </span>
    );
  }
  if (ranks.state === 'unranked') {
    return (
      <span
        className="sv-quote-rank sv-quote-rank--none"
        data-testid="stock-view-quote-rank"
        {...tipProps(
          `${symbol} is on none of the scanner lists${ranks.replay ? ' at the Sim playhead' : ''} `
            + '(Gappers, Gainers, Losers, After Hours, Large Cap).',
          'Not on a list',
        )}
      >
        Not on a list
      </span>
    );
  }
  return (
    <span className="sv-quote-ranks" data-testid="stock-view-quote-rank">
      {ranks.ranks.map((r) => (
        <span
          key={r.list}
          className={`sv-quote-rank${r.rank <= RANK_LEADER_MAX ? ' sv-quote-rank--lead' : ''}`}
          data-list={r.list}
          {...tipProps(rankTip(r, ranks.replay), `#${r.rank} on ${r.label}`)}
        >
          <span className="sv-quote-rank__num">#{r.rank}</span>
          <span className="sv-quote-rank__list">{r.label}</span>
        </span>
      ))}
    </span>
  );
});
