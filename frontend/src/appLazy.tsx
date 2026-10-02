/** App-shell lazy pages -- keep the scanner Dashboard in the first chunk. */
import { lazy } from 'react';

export const LazySampleShell = lazy(() =>
  import('./sample_data/SampleShell').then(m => ({ default: m.SampleShell })),
);

export const LazyStockViewTabs = lazy(() =>
  import('./stock_view/StockViewTabs').then(m => ({ default: m.StockViewTabs })),
);

/** The public demo's strip (ADR 043); null in every other build. */
export const LazyDemoStrip = import.meta.env.VITE_NOVA_DEMO === '1' ? lazy(() => import('./demo/DemoStrip')) : null;
