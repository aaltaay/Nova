/**
 * The candle series reads to the stock's tick: its axis, last-price chip and price lines all take
 * their digits from the series, and lightweight-charts stops at two. A pane changes symbol in place,
 * so the digits follow the price it is painting, in both directions.
 */
import type { ISeriesApi } from 'lightweight-charts';
import { priceDigits, priceStep } from '../utils/priceTick';

const painted = new WeakMap<object, number>();

export function keepPriceDigits(series: ISeriesApi<'Candlestick'> | null, price: number | undefined): void {
  if (!series || price == null || !Number.isFinite(price)) return;
  const precision = priceDigits(price);
  if (painted.get(series) === precision) return;
  painted.set(series, precision);
  series.applyOptions({ priceFormat: { type: 'price', precision, minMove: priceStep(price) } });
}
