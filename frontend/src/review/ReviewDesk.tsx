/** One symbol: the desk grid, toolbar and key, filled from a review payload. */

import { useEffect, useMemo, useState } from 'react';
import { ChartGridToolbar } from '../components/ChartGridToolbar';
import {
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_PANE_INDICATORS,
  type ChartIndicatorId,
} from '../constants';
import { cutPayload, fetchReview } from './reviewData';
import { fixturePayload, type ReviewPayload } from './reviewFixture';
import { ReviewPane } from './ReviewPane';
import { TF_PANE, type ReviewQuery, type ReviewTf } from './reviewQuery';

function defaults(tf: ReviewTf): ChartIndicatorId[] {
  return [...(CHART_GRID_PANE_INDICATORS[TF_PANE[tf].id] ?? CHART_DEFAULT_INDICATORS)];
}

interface Props {
  query: ReviewQuery;
  symbol: string;
  onReady: (state: '1' | 'error') => void;
}

export function ReviewDesk({ query, symbol, onReady }: Props) {
  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [painted, setPainted] = useState<Record<string, boolean>>({});
  const [focus, setFocus] = useState<ReviewTf>(query.tfs[0] ?? '5m');
  const [tool, setTool] = useState<string | null>(null);
  const [clearToken, setClearToken] = useState(0);
  const [indicators, setIndicators] = useState<Record<string, ChartIndicatorId[]>>({});
  const tfKey = query.tfs.join(',');

  useEffect(() => {
    let cancel = false;
    setPayload(null);
    setError(null);
    setPainted({});
    const load = query.fixture
      ? Promise.resolve(fixturePayload(symbol, query.date, query.tfs, query.asOf))
      : fetchReview(symbol, query.date, query.tfs, query.asOf, query.api);
    load
      .then((body) => { if (!cancel) setPayload(cutPayload(body)); })
      .catch((err: unknown) => { if (!cancel) setError(err instanceof Error ? err.message : String(err)); });
    return () => { cancel = true; };
  }, [symbol, query.date, query.asOf, query.fixture, query.api, tfKey, query.tfs]);

  useEffect(() => {
    setIndicators(Object.fromEntries(query.tfs.map((tf) => [tf, defaults(tf)])));
    setFocus(query.tfs[0] ?? '5m');
  }, [tfKey, query.tfs]);

  const shown = query.tfs;
  const vwapBars = payload?.timeframes['1m']?.bars ?? payload?.timeframes['5m']?.bars ?? [];
  const ready = error ? 'error' : payload && shown.every((tf) => painted[tf]) ? '1' : '0';

  useEffect(() => {
    if (ready === '1' || ready === 'error') onReady(ready);
  }, [ready, onReady]);

  const emptyLevels = useMemo(() => ({
    hod: null, lod: null, premarket_high: null, opening_range_high: null, opening_range_low: null,
    prior_high: null, prior_low: null, prior_close: null,
  }), []);

  const toggle = (tf: ReviewTf, id: ChartIndicatorId) => {
    setIndicators((prev) => {
      const current = prev[tf] ?? defaults(tf);
      const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
      return { ...prev, [tf]: next };
    });
  };

  return (
    <div className="review-desk">
      {error && <p className="review-error" role="alert">{error}</p>}
      {!error && payload && (
        <>
          <ChartGridToolbar
            activeTool={tool}
            focusedLabel={TF_PANE[focus].label}
            focusedIndicators={indicators[focus] ?? []}
            maximized={false}
            onToolClick={(id) => setTool((prev) => (prev === id ? null : id))}
            onClearAll={() => setClearToken((n) => n + 1)}
            onIndicatorToggle={(id) => toggle(focus, id)}
            onRestore={() => {}}
          />
          <div className={`review-grid review-grid--${shown.length}`}>
            {shown.map((tf) => (
              <ReviewPane
                key={tf}
                symbol={symbol}
                date={query.date}
                tf={tf}
                bars={payload.timeframes[tf]?.bars ?? []}
                vwapBars={vwapBars}
                levels={payload.levels ?? emptyLevels}
                setups={tf === '5m' || tf === '1m' ? payload.setups : []}
                enabled={indicators[tf] ?? defaults(tf)}
                activeTool={focus === tf ? tool : null}
                clearToken={focus === tf ? clearToken : 0}
                onPainted={() => setPainted((prev) => (prev[tf] ? prev : { ...prev, [tf]: true }))}
                onFocus={() => setFocus(tf)}
                onIndicatorToggle={(id) => toggle(tf, id)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
