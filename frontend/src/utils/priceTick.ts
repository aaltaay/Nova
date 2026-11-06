/**
 * A US stock's listed tick: a cent at $1 and over, a hundredth of a cent under it. The ticket, the
 * hotkeys and the chart read the rule here, so a 0.3456 bid is sent, shown and drawn as 0.3456.
 *
 * `at` is the stock price the tick belongs to, for a figure that is not itself the stock's price:
 * a 0.0537 trail on a 5.37 stock still moves in cents.
 */
const SUBPENNY_UNDER = 1;

export function priceDigits(price: number): 2 | 4 {
  return Math.abs(price) < SUBPENNY_UNDER ? 4 : 2;
}

export function priceStep(price: number): 0.01 | 0.0001 {
  return priceDigits(price) === 4 ? 0.0001 : 0.01;
}

export function roundToTick(price: number, at: number = price): number {
  return Number(price.toFixed(priceDigits(at)));
}

/** The price with no dollar sign, up to four digits: 0.3456, 0.345, 0.34, 12.34. */
export function plainPrice(price: number, at: number = price): string {
  const digits = priceDigits(at);
  const text = price.toFixed(digits);
  return digits === 4 ? text.replace(/0{1,2}$/, '') : text;
}
