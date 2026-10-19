/** A grid of mini desk charts. Each cell loads when it mounts and links to that symbol. */

import { useCallback, useEffect, useState } from 'react';
import { CHART_GRID_PANE_INDICATORS, type ChartIndicatorId } from '../constants';
import { cutPayload, fetchReview } from './reviewData';
import { fixturePayload, type ReviewPayload } from './reviewFixture';
import { ReviewPane } from './ReviewPane';
import { reviewHref, type ReviewQuery } from './reviewQuery';

interface Props {
  query: ReviewQuery;
  onReady: (state: '1' | 'error') => void;
}

function Cell({
  symbol, query, onPainted, onFailed,
}: {
  symbol: string;
  query: ReviewQuery;
  onPainted: (symbol: string) => void;
  onFailed: () => void;
}) {
  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mark = useCallback(() => onPainted(symbol), [onPainted, symbol]);

  useEffect(() => {
    let cancel = false;
    const load = query.fixture
      ? Promise.resolve(fixturePayload(symbol, query.date, ['5m'], query.asOf))
      : fetchReview(symbol, query.date, ['5m'], query.asOf);
    load
      .then((body) => { if (!cancel) setPayload(cutPayload(body)); })
      .catch((err: unknown) => {
        if (!cancel) {
          setError(err instanceof Error ? err.message : String(err));
          onFailed();
        }
      });
    return () => { cancel = true; };
  }, [symbol, query.date, query.asOf, query.fixture]);

  const href = reviewHref(symbol, query.date, query.tfs, query.asOf, query.fixture);
  return (
    <article className="review-cell">
      <a className="review-cell__link" href={href}>{symbol}</a>
      {error && <p className="review-error" role="alert">{error}</p>}
      {payload && (
        <ReviewPane
          symbol={symbol}
          date={query.date}
          tf="5m"
          bars={payload.timeframes['5m']?.bars ?? []}
          vwapBars={payload.timeframes['1m']?.bars ?? []}
          levels={payload.levels}
          setups={payload.setups}
          enabled={[...(CHART_GRID_PANE_INDICATORS['5Min'] ?? [])] as ChartIndicatorId[]}
          activeTool={null}
          clearToken={0}
          onPainted={mark}
          onFocus={() => {}}
          onIndicatorToggle={() => {}}
        />
      )}
    </article>
  );
}

export function ReviewGallery({ query, onReady }: Props) {
  const [painted, setPainted] = useState<Record<string, boolean>>({});
  const [failed, setFailed] = useState(false);
  const onPainted = useCallback((symbol: string) => {
    setPainted((prev) => (prev[symbol] ? prev : { ...prev, [symbol]: true }));
  }, []);

  useEffect(() => {
    if (failed) onReady('error');
    else if (query.symbols.length > 0 && query.symbols.every((symbol) => painted[symbol])) onReady('1');
  }, [failed, painted, query.symbols, onReady]);

  return (
    <div className={`review-gallery review-gallery--${Math.min(query.symbols.length, 9)}`}>
      {query.symbols.map((symbol) => (
        <Cell key={symbol} symbol={symbol} query={query} onPainted={onPainted} onFailed={() => setFailed(true)} />
      ))}
      {failed && <p className="review-error" role="alert">A chart failed to load.</p>}
    </div>
  );
}
