import { useEffect } from 'react';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { TRADER_DRAFT_SYMBOL } from '../stock_view/traderTabsState';
import { syncTraderLive } from './api';

/**
 * UI reports live L2 tabs so bot Eyes share the max-3 cap. Never from the
 * sample desk: WorkspaceProvider sits above the sample shell, and its empty
 * tab list used to overwrite the live bot's Trader list on every load (V4).
 * Leaving the sample desk re-sends the live list.
 */
export function useBotFocusSync(live: string[]): void {
  const sampleRoute = useSampleRoute();
  const key = live.filter(s => s && s !== TRADER_DRAFT_SYMBOL).join(',');
  useEffect(() => {
    if (sampleRoute) return;
    const symbols = key ? key.split(',') : [];
    void syncTraderLive(symbols);
  }, [key, sampleRoute]);
}
