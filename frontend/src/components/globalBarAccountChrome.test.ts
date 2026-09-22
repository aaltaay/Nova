import { describe, expect, it } from 'vitest';
import { resolveAccountChromeState } from './globalBarAccountChrome';

describe('resolveAccountChromeState', () => {
  it('is offline only when Gateway session is down', () => {
    expect(
      resolveAccountChromeState({
        ibkrConnected: false,
        summaryConnected: undefined,
        loading: false,
        error: null,
      }),
    ).toBe('offline');
  });

  it('is loading when Gateway is up but account summary not ready', () => {
    expect(
      resolveAccountChromeState({
        ibkrConnected: true,
        summaryConnected: undefined,
        loading: true,
        error: null,
      }),
    ).toBe('loading');
    // First paint before poll — still loading, never "offline"
    expect(
      resolveAccountChromeState({
        ibkrConnected: true,
        summaryConnected: undefined,
        loading: false,
        error: null,
      }),
    ).toBe('loading');
  });

  it('is unavailable when Gateway is up but account poll failed', () => {
    expect(
      resolveAccountChromeState({
        ibkrConnected: true,
        summaryConnected: undefined,
        loading: false,
        error: 'account (HTTP 503)',
      }),
    ).toBe('unavailable');
  });

  it('is ready when Gateway and account summary are both connected', () => {
    expect(
      resolveAccountChromeState({
        ibkrConnected: true,
        summaryConnected: true,
        loading: false,
        error: null,
      }),
    ).toBe('ready');
  });

  it('never says "IBKR offline" while the status itself is unknown (QA D10)', () => {
    const unknown = { ibkrConnected: false, summaryConnected: undefined, loading: false, error: null };
    expect(resolveAccountChromeState({ ...unknown, statusKnown: false, statusError: null })).toBe('loading');
    expect(resolveAccountChromeState({ ...unknown, statusKnown: false, statusError: 'HTTP 500' })).toBe('unavailable');
    // A current answer that says the Gateway is down is still offline.
    expect(resolveAccountChromeState({ ...unknown, statusKnown: true, statusError: null })).toBe('offline');
  });
});

