/** The /review page. Read only: no order ticket and no live feed. */

import { useCallback, useMemo, useState } from 'react';
import { ReviewDesk } from './ReviewDesk';
import { ReviewGallery } from './ReviewGallery';
import { galleryFrame, parseReviewQuery, TF_PANE } from './reviewQuery';

export function ReviewApp() {
  const query = useMemo(() => parseReviewQuery(window.location.search), []);
  const [ready, setReady] = useState<'0' | '1' | 'error'>('0');
  const onReady = useCallback((state: '1' | 'error') => setReady(state), []);
  const source = query.fixture ? 'fixture' : 'front-door';
  const title = query.gallery ? query.symbols.join(' ') : query.symbols[0];
  const frameLabel = query.gallery ? `${TF_PANE[galleryFrame(query.tfs)].label} only` : '';

  if (!query.symbols.length || !query.date) {
    return (
      <div className="review-app" data-review-ready="error" data-review-source={source}>
        <p className="review-error" role="alert">
          Add a symbol and a date. Example: /review?symbol=IMCC&amp;date=2026-09-18&amp;tf=1m,5m,1d
        </p>
      </div>
    );
  }

  return (
    <div className="review-app" data-review-ready={ready} data-review-source={source}>
      <header className="review-header">
        <strong>{title}</strong>
        <span>{query.date}</span>
        {frameLabel && <span>{frameLabel}</span>}
        <span>as of {query.asOf} ET</span>
        <span>{query.fixture ? 'Fixture' : 'Front door'}</span>
        <span className="review-header__note">Read only. No orders.</span>
      </header>
      {query.gallery
        ? <ReviewGallery query={query} onReady={onReady} />
        : <ReviewDesk query={query} symbol={query.symbols[0]} onReady={onReady} />}
    </div>
  );
}
