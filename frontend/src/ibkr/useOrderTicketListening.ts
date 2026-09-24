/**
 * Whether a mounted order ticket in this window takes prefills for `symbol`
 * (#566). A prefill nobody hears is dropped, so a sender that cannot queue --
 * the chart menu's priced rows -- locks itself with a reason while this is false.
 */
import { useCallback, useSyncExternalStore } from 'react';
import { orderTicketListening, watchOrderTicketListening } from './orderTicketPrefill';

export function useOrderTicketListening(symbol: string): boolean {
  const read = useCallback(() => orderTicketListening(symbol), [symbol]);
  return useSyncExternalStore(watchOrderTicketListening, read, () => false);
}
