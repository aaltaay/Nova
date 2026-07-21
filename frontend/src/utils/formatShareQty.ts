/**
 * Display share quantities with fractional precision (Webull-style).
 * Whole shares stay compact (100 → "100"); fractions keep up to
 * TICKER_TRADE_QTY_DECIMALS digits (0.0642 → "0.0642").
 */
import { TICKER_TRADE_QTY_DECIMALS } from '../constants';

export function formatShareQty(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: TICKER_TRADE_QTY_DECIMALS,
  });
}
