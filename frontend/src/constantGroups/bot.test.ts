import { describe, expect, it } from 'vitest';
import {
  BOT_GATE_LABELS,
  BOT_GATE_TIPS,
  BOT_SETUP_BLURBS,
  BOT_SETUP_IDS,
  BOT_SETUP_LABELS,
  BOT_SETUP_RESEARCH,
  BOT_SYMBOL_ALLOWLIST_CAP,
  botTradeAddLabel,
  botTradeRemoveLabel,
} from './bot';

describe('bot playbook copy (ADR 027)', () => {
  it('names, describes and grades every setup the backend lists', () => {
    // Mirrors backend/constants_bot.py BOT_SETUPS.
    expect([...BOT_SETUP_IDS]).toEqual(
      ['first_pullback', 'bull_flag', 'flat_top_breakout', 'red_to_green', 'gap_and_go', 'micro_pullback']);
    for (const id of BOT_SETUP_IDS) {
      expect(BOT_SETUP_LABELS[id].length).toBeGreaterThan(3);
      expect(BOT_SETUP_BLURBS[id].length).toBeGreaterThan(20);
      expect(BOT_SETUP_RESEARCH[id].text.length).toBeGreaterThan(10);
    }
  });

  it('labels and explains every gate backend/bot/gates.py returns (ADR 042 C)', () => {
    const ids = ['allowlist', 'bot_trip', 'commissions', 'daily_cap', 'day_lock', 'depth_lines', 'extended_hours',
      'kill_switch', 'level', 'padlock', 'setups', 'venue', 'window'];
    expect(Object.keys(BOT_GATE_LABELS).sort()).toEqual(ids);
    expect(Object.keys(BOT_GATE_TIPS).sort()).toEqual(ids);
  });

  it('mirrors the backend cap on the bot’s stocks', () => {
    expect(BOT_SYMBOL_ALLOWLIST_CAP).toBe(50);
  });

  it('never says "allowlist" where the operator reads it: the bot trades a stock, or it does not', () => {
    expect(botTradeAddLabel('GRML')).toBe('Let the bot trade GRML (bot buys and sells)');
    expect(botTradeRemoveLabel('GRML')).toBe('Stop the bot trading GRML');
  });
});
