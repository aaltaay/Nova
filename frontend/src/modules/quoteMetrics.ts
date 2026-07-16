/** Pure quote-price / description helpers shared by quote panels. */
import type { TickerDetail } from '../types/ticker';
import { sessionPriceOrNull } from '../utils/quoteFormat';

export type QuoteMetrics = {
  mainPrice: number | null;
  mainChangeAbs: number | null;
  mainChangePct: number | null;
  extPrice: number | null;
  extChangeAbs: number | null;
  extChangePct: number | null;
  extLabel: string;
  extIsPositive: boolean;
  isExtendedHours: boolean;
  isPositive: boolean;
  lastUpdated: string | null;
  prevClose: number | null;
  gapPct: number | null;
  descParts: string[];
};

export function computeQuoteMetrics(
  detail: TickerDetail,
  discoveryProvider: string,
): QuoteMetrics {
  const snap = detail.snapshot;
  const asset = detail.asset;
  const trade = snap?.latest_trade;
  const daily = snap?.daily_bar;
  const prevClose = snap?.prev_close ?? snap?.prev_daily_bar?.close ?? null;
  const useIbkrUnifiedQuote = discoveryProvider === 'ibkr';
  const isExtendedHours =
    !useIbkrUnifiedQuote && (detail.mode === 'premarket' || detail.mode === 'afterhours');
  const sessionClose = snap?.session_close ?? null;
  const sessionPrevClose = snap?.session_prev_close ?? null;
  const livePrice = trade?.price ?? daily?.close ?? null;
  const mainPrice = useIbkrUnifiedQuote
    ? livePrice
    : (isExtendedHours ? sessionClose : livePrice);
  const mainPrevRef = useIbkrUnifiedQuote
    ? prevClose
    : (isExtendedHours ? sessionPrevClose : prevClose);
  const mainChangeAbs =
    mainPrice != null && mainPrevRef != null ? mainPrice - mainPrevRef : null;
  const mainChangePct =
    mainChangeAbs != null && mainPrevRef ? mainChangeAbs / mainPrevRef : null;
  const extPrice = isExtendedHours ? livePrice : null;
  const extChangeAbs =
    extPrice != null && sessionClose != null ? extPrice - sessionClose : null;
  const extChangePct =
    extChangeAbs != null && sessionClose ? extChangeAbs / sessionClose : null;
  const extLabel = detail.mode === 'premarket' ? 'Pre' : 'After';
  const extIsPositive = (extChangePct ?? 0) >= 0;
  const isPositive = isExtendedHours ? extIsPositive : (mainChangePct ?? 0) >= 0;
  const lastUpdated = trade?.timestamp ?? snap?.latest_quote?.timestamp ?? null;

  const descParts: string[] = [];
  if (asset?.name) descParts.push(asset.name);
  if (asset?.exchange) descParts.push(asset.exchange);
  if (detail.fundamentals?.sector) descParts.push(detail.fundamentals.sector);
  if (detail.fundamentals?.industry) descParts.push(detail.fundamentals.industry);

  const todayOpen = sessionPriceOrNull(daily?.open);
  const gapPct =
    todayOpen != null && prevClose != null && prevClose !== 0
      ? (todayOpen - prevClose) / prevClose
      : null;

  return {
    mainPrice,
    mainChangeAbs,
    mainChangePct,
    extPrice,
    extChangeAbs,
    extChangePct,
    extLabel,
    extIsPositive,
    isExtendedHours,
    isPositive,
    lastUpdated,
    prevClose,
    gapPct,
    descParts,
  };
}
