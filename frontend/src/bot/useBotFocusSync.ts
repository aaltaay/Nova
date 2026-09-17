import { useEffect } from 'react';
import { TRADER_DRAFT_SYMBOL } from '../stock_view/traderTabsState';
import { syncTraderLive } from './api';

/** UI reports live L2 tabs so bot Eyes share the max-3 cap. */
export function useBotFocusSync(live: string[]): void {
  const key = live.filter(s => s && s !== TRADER_DRAFT_SYMBOL).join(',');
  useEffect(() => {
    const symbols = key ? key.split(',') : [];
    void syncTraderLive(symbols);
  }, [key]);
}
