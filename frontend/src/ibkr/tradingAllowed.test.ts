import { describe, expect, it } from 'vitest';
import {
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
  NOVA_ACTION_PIN_LOCKED_MESSAGE,
} from '../constants';
import {
  botArmDisplayState,
  evaluateTradingAllowed,
  padlockLooksUnlocked,
} from './tradingAllowed';

describe('evaluateTradingAllowed', () => {
  it('allows only when connected, spend/backend, and PIN agree', () => {
    const gate = evaluateTradingAllowed({
      connected: true,
      spendStatus: 'paper_armed',
      sessionUnlocked: true,
      backendAllowed: true,
    });
    expect(gate).toEqual({ allowed: true, reason: null, blockers: [] });
    expect(padlockLooksUnlocked(gate)).toBe(true);
  });

  it('does not look unlocked when PIN is locked even if backend allows', () => {
    const gate = evaluateTradingAllowed({
      connected: true,
      spendStatus: 'paper_armed',
      sessionUnlocked: false,
      backendAllowed: true,
    });
    expect(gate.allowed).toBe(false);
    expect(gate.blockers).toEqual(['pin']);
    expect(gate.reason).toBe(NOVA_ACTION_PIN_LOCKED_MESSAGE);
    expect(padlockLooksUnlocked(gate)).toBe(false);
  });

  it('does not look unlocked when backend spend blocks even if PIN is open', () => {
    const gate = evaluateTradingAllowed({
      connected: true,
      spendStatus: 'paper_armed',
      sessionUnlocked: true,
      backendAllowed: false,
      backendReason: 'Orders locked -- IBKR_ORDERS_ENABLED is off',
    });
    expect(gate.allowed).toBe(false);
    expect(gate.blockers).toEqual(['spend']);
    expect(gate.reason).toMatch(/ORDERS_ENABLED/);
    expect(padlockLooksUnlocked(gate)).toBe(false);
  });

  it('counts the padlock once when it is the only lock (spec D)', () => {
    // The backend's trading_allowed already includes the arm latch: disarmed is the padlock,
    // never also a "spend" lock, so the ticket offers Unlock without a second lock note.
    const gate = evaluateTradingAllowed({
      connected: true,
      spendStatus: 'locked_disarmed',
      sessionUnlocked: false,
      backendAllowed: false,
      backendReason: 'Desk is disarmed -- arm trading in this session before placing',
    });
    expect(gate.allowed).toBe(false);
    expect(gate.blockers).toEqual(['pin']);
    expect(gate.reason).toMatch(/disarmed/);
    const noBackend = evaluateTradingAllowed({ connected: true, spendStatus: 'locked_disarmed', sessionUnlocked: false });
    expect(noBackend.blockers).toEqual(['pin']);
  });

  it('keeps a second blocker when the backend refuses for something besides the padlock', () => {
    const gate = evaluateTradingAllowed({
      connected: true,
      spendStatus: 'locked_disarmed',
      sessionUnlocked: false,
      backendAllowed: false,
      backendReason: 'IBKR session not ready',
    });
    expect(gate.blockers).toEqual(['spend', 'pin']);
    expect(gate.reason).toBe('IBKR session not ready');
  });

  it('Activate must not look Active when places are blocked', () => {
    const blocked = evaluateTradingAllowed({
      connected: true,
      spendStatus: 'paper_armed',
      sessionUnlocked: false,
      backendAllowed: true,
    });
    const display = botArmDisplayState(true, blocked);
    expect(display.looksActive).toBe(false);
    expect(display.label).toContain(BOT_STATE_ACTIVE);
    expect(display.label).toContain(NOVA_ACTION_PIN_LOCKED_MESSAGE);
    expect(botArmDisplayState(true, {
      allowed: true,
      reason: null,
      blockers: [],
    })).toEqual({ label: BOT_STATE_ACTIVE, looksActive: true });
    expect(botArmDisplayState(false, blocked)).toEqual({
      label: BOT_STATE_NOT_ACTIVE,
      looksActive: false,
    });
  });
});
