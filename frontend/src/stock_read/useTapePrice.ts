/**
 * The tab's price as its tape moves, for what the plan box draws from it (operator report 2026-10-13: the held
 * ruler's price tick "doesn't look smooth at all ... way too delayed" -- it moved once a read, every 5 s). Live
 * and Paper (and Sim at the live edge) read the line's last trade, at most once a frame; a Sim tab off the live
 * edge reads the replay's at the playhead, as the quote head does. With neither, the read's own price.
 */
import { tickerLastTrade } from '../hooks/tickerStore';
import { useTickerFrameSelect } from '../hooks/useTickerStream';
import { useVenuePrice } from '../sim';

export function useTapePrice(symbol: string, fallback: number | null): number | null {
  const sym = symbol.trim().toUpperCase();
  const last = useTickerFrameSelect(sym, (state) => tickerLastTrade(state, sym)?.price ?? null);
  return useVenuePrice(sym, last).price ?? fallback;
}
