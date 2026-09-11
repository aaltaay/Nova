import {
  EARNINGS_NO_KEY_MESSAGE,
  EARNINGS_MISSING_KEY_STALE_MESSAGE,
  EARNINGS_RATE_LIMITED_MESSAGE,
  EARNINGS_RATE_LIMITED_STALE_MESSAGE,
} from '../constants';

/** Map backend error tokens to operator copy. Unknown strings pass through. */
export function earningsErrorCopy(error: string | null, hasRows: boolean): string | null {
  if (!error) return null;
  if (error === 'missing_key') {
    return hasRows ? EARNINGS_MISSING_KEY_STALE_MESSAGE : EARNINGS_NO_KEY_MESSAGE;
  }
  if (error === 'rate_limited') {
    return hasRows ? EARNINGS_RATE_LIMITED_STALE_MESSAGE : EARNINGS_RATE_LIMITED_MESSAGE;
  }
  return error;
}
