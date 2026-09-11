/** App-shell lazy pages -- keep the scanner Dashboard in the first chunk. */
import { lazy } from 'react';

export const LazySampleShell = lazy(() =>
  import('./sample_data/SampleShell').then(m => ({ default: m.SampleShell })),
);

export const LazyStockViewTabs = lazy(() =>
  import('./stock_view/StockViewTabs').then(m => ({ default: m.StockViewTabs })),
);
