/** Persist “don’t show place-order confirm again” preference. */
import { TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY } from '../constants';

export function readSkipPlaceConfirm(): boolean {
  try {
    return localStorage.getItem(TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeSkipPlaceConfirm(skip: boolean): void {
  try {
    if (skip) {
      localStorage.setItem(TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY, '1');
    } else {
      localStorage.removeItem(TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY);
    }
  } catch {
    /* private mode / quota */
  }
}
