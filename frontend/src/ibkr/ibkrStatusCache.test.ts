/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import { readLastIbkrStatus, writeLastIbkrStatus } from './ibkrStatusCache';
import type { IbkrStatus } from './types';

const sample: IbkrStatus = {
  enabled: true,
  connected: true,
  transport_connected: true,
  session_reason: 'ok',
  mode: 'paper',
  gateway_mode: 'paper',
  market_data_delayed: true,
  orders_enabled: true,
  spend_status: 'paper_armed',
};

afterEach(() => {
  sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
});

describe('ibkrStatusCache', () => {
  it('round-trips last-good status for this tab', () => {
    expect(readLastIbkrStatus()).toBeNull();
    writeLastIbkrStatus(sample);
    expect(readLastIbkrStatus()).toMatchObject({
      connected: true,
      mode: 'paper',
      market_data_delayed: true,
    });
  });

  it('rejects junk', () => {
    sessionStorage.setItem(IBKR_STATUS_SESSION_KEY, '{"nope":true}');
    expect(readLastIbkrStatus()).toBeNull();
  });
});
