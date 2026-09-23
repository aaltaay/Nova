import { describe, expect, it, vi } from 'vitest';
import { consumeFocusListRequest, requestFocusList, subscribeFocusListRequest } from './focusListRequest';

describe('focusListRequest', () => {
  it('latches the last list until consumed, once', () => {
    consumeFocusListRequest();
    requestFocusList('losers');
    requestFocusList('gainers');
    expect(consumeFocusListRequest()).toBe('gainers');
    expect(consumeFocusListRequest()).toBeNull();
  });

  it('ignores an open with no list or an id that is not a tab module', () => {
    consumeFocusListRequest();
    requestFocusList(undefined);
    requestFocusList('');
    requestFocusList('not_a_list');
    expect(consumeFocusListRequest()).toBeNull();
  });

  it('announces each request to subscribers until they leave', () => {
    const listener = vi.fn();
    const leave = subscribeFocusListRequest(listener);
    requestFocusList('hod_momo');
    expect(listener).toHaveBeenCalledTimes(1);
    leave();
    requestFocusList('gappers');
    expect(listener).toHaveBeenCalledTimes(1);
    consumeFocusListRequest();
  });
});
