/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY } from '../constants';
import { readSkipPlaceConfirm, writeSkipPlaceConfirm } from './placeConfirmPrefs';

describe('placeConfirmPrefs', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to showing the confirm dialog', () => {
    expect(readSkipPlaceConfirm()).toBe(false);
  });

  it('persists skip preference', () => {
    writeSkipPlaceConfirm(true);
    expect(readSkipPlaceConfirm()).toBe(true);
    expect(localStorage.getItem(TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY)).toBe('1');
    writeSkipPlaceConfirm(false);
    expect(readSkipPlaceConfirm()).toBe(false);
  });
});
