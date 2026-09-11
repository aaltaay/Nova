import { describe, expect, it } from 'vitest';
import {
  EARNINGS_NO_KEY_MESSAGE,
  EARNINGS_MISSING_KEY_STALE_MESSAGE,
  EARNINGS_RATE_LIMITED_MESSAGE,
  EARNINGS_RATE_LIMITED_STALE_MESSAGE,
} from '../constants';
import { earningsErrorCopy } from './earningsError';

describe('earningsErrorCopy', () => {
  it('maps missing_key to the no-key banner when the tab is empty', () => {
    expect(earningsErrorCopy('missing_key', false)).toBe(EARNINGS_NO_KEY_MESSAGE);
  });

  it('maps missing_key to a stale-cache banner when rows exist', () => {
    expect(earningsErrorCopy('missing_key', true)).toBe(EARNINGS_MISSING_KEY_STALE_MESSAGE);
  });

  it('maps rate_limited with and without rows', () => {
    expect(earningsErrorCopy('rate_limited', false)).toBe(EARNINGS_RATE_LIMITED_MESSAGE);
    expect(earningsErrorCopy('rate_limited', true)).toBe(EARNINGS_RATE_LIMITED_STALE_MESSAGE);
  });

  it('passes through unknown backend strings', () => {
    expect(earningsErrorCopy('Finnhub request failed', false)).toBe('Finnhub request failed');
  });
});
