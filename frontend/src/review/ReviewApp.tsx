/** The /review page. The desk chart, fed by a recorded day. No orders and no live feed. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChartGrid } from '../components/ChartGrid';
import { ChartFeedProvider } from '../chart';
import { fetchReview, cutPayload } from './reviewData';
import { fixturePayload, type ReviewPayload } from './reviewFixture';
import { feedFromPayload } from './reviewFeed';
import { GalleryBoard } from './GalleryBoard';
import { levelOverlay } from './RecordedLevelsOverlay';
import { parseReviewQuery, TF_PANE, REVIEW_TFS, type ReviewTf } from './reviewQuery';
import { ReviewSymbolButton } from './ReviewSymbolButton';

function loadOne(symbol: string, date: string, asOf: string, fixture: boolean, api: string): Promise<ReviewPayload> {
  if (fixture) return Promise.resolve(fixturePayload(symbol, date, [...REVIEW_TFS], asOf));
  return fetchReview(symbol, date, [...REVIEW_TFS], asOf, api);
}

export function ReviewApp() {
  const query = useMemo(() => parseReviewQuery(window.location.search), []);
  const [gtf, setGtf] = useState<ReviewTf>(query.gtf);
  const [payloads, setPayloads] = useState<ReviewPayload[] | null>(null);
  const [ready, setReady] = useState<'0' | '1' | 'error'>('0');
  const [openNote, setOpenNote] = useState<string | null>(null);
  const source = query.fixture ? 'fixture' : 'front-door';
  const paintKey = query.gallery ? `${gtf}` : query.symbols.join(',');
  const expected = query.gallery ? query.symbols.length : 4;
  const bucket = useRef({ key: '', ids: new Set<string>() });
  const [shownKey, setShownKey] = useState(paintKey);
  if (shownKey !== paintKey) {
    setShownKey(paintKey);
    setReady('0');
    bucket.current = { key: paintKey, ids: new Set() };
  }

  useEffect(() => {
    const onPop = () => setGtf(parseReviewQuery(window.location.search).gtf);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  useEffect(() => {
    if (!query.symbols.length || !query.date) return;
    let cancel = false;
    setPayloads(null);
    Promise.all(query.symbols.map((symbol) => loadOne(symbol, query.date, query.asOf, query.fixture, query.api)))
      .then((rows) => {
        if (!cancel) setPayloads(rows.map(cutPayload));
      })
      .catch(() => {
        if (!cancel) setReady('error');
      });
    return () => {
      cancel = true;
    };
  }, [query]);

  const onPanePainted = useCallback((id: string) => {
    if (bucket.current.key !== paintKey) bucket.current = { key: paintKey, ids: new Set() };
    bucket.current.ids.add(id);
    if (bucket.current.ids.size >= expected) setReady('1');
  }, [paintKey, expected]);

  const onSelect = useCallback((tf: ReviewTf) => {
    const params = new URLSearchParams(window.location.search);
    params.set('gtf', tf);
    window.history.pushState(null, '', `${window.location.pathname}?${params.toString()}`);
    setGtf(tf);
  }, []);

  if (!query.symbols.length || !query.date) {
    return (
      <div className="review-app" data-review-ready="error" data-review-source={source}>
        <p className="review-error" role="alert">
          Add a symbol and a date. Example: /review?symbol=IMCC&amp;date=2026-09-18
        </p>
      </div>
    );
  }

  const title = query.gallery ? query.symbols.join(' ') : query.symbols[0];
  const frameLabel = query.gallery ? TF_PANE[gtf].label : '';
  const desk = !query.gallery && payloads?.[0];
  const feed = desk ? feedFromPayload(desk) : null;

  return (
    <div className="review-app" data-review-ready={payloads ? ready : '0'} data-review-source={source}>
      <header className="review-header">
        {query.gallery ? <strong>{title}</strong> : (
          <ReviewSymbolButton
            symbol={query.symbols[0]}
            date={query.date}
            asOf={query.asOf}
            onNote={setOpenNote}
            showNote={false}
          />
        )}
        <span>{query.date}</span>
        {frameLabel && <span>{frameLabel}</span>}
        <span>as of {query.asOf} ET</span>
        <span>{query.fixture ? 'Fixture' : 'Front door'}</span>
        <span className="review-header__note">Read only. No orders.</span>
        {openNote ? <span className="review-open__note" role="status">{openNote}</span> : null}
      </header>
      {query.gallery
        ? payloads && (
          <GalleryBoard
            query={query}
            gtf={gtf}
            payloads={payloads}
            onSelect={onSelect}
            onPanePainted={onPanePainted}
          />
        )
        : feed && desk && (
          <div className="review-desk">
            <ChartFeedProvider feed={feed} onPanePainted={onPanePainted}>
              <ChartGrid
                symbol={desk.symbol}
                renderPaneOverlay={levelOverlay(desk.levels, desk.setups)}
                toolbarExtra={(
                  <ReviewSymbolButton
                    symbol={desk.symbol}
                    date={query.date}
                    asOf={query.asOf}
                    showNote={false}
                    onNote={setOpenNote}
                  />
                )}
              />
            </ChartFeedProvider>
          </div>
        )}
    </div>
  );
}
