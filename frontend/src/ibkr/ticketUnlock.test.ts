/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import {
  TICKER_TRADE_UNLOCK_PIN,
  TICKER_TRADE_UNLOCK_SESSION_KEY,
} from '../constants';
import {
  readTicketSessionUnlocked,
  tryUnlockTicketSession,
  writeTicketSessionUnlocked,
} from './ticketUnlock';

describe('ticketUnlock', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('starts locked', () => {
    expect(readTicketSessionUnlocked()).toBe(false);
  });

  it('unlocks only with the configured PIN', () => {
    expect(tryUnlockTicketSession('000000')).toBe(false);
    expect(readTicketSessionUnlocked()).toBe(false);
    expect(tryUnlockTicketSession(TICKER_TRADE_UNLOCK_PIN)).toBe(true);
    expect(readTicketSessionUnlocked()).toBe(true);
    expect(sessionStorage.getItem(TICKER_TRADE_UNLOCK_SESSION_KEY)).toBe('1');
  });

  it('persists unlock for the session', () => {
    writeTicketSessionUnlocked(true);
    expect(readTicketSessionUnlocked()).toBe(true);
    writeTicketSessionUnlocked(false);
    expect(readTicketSessionUnlocked()).toBe(false);
  });
});
