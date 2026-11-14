import { describe, expect, it } from 'vitest';
import { BOT_SETUP_IDS, BOT_SETUP_LABELS } from './bot';

describe('bot playbook copy (ADR 027)', () => {
  it('names every setup the backend lists', () => {
    // Mirrors backend/constants_bot.py BOT_SETUPS.
    expect([...BOT_SETUP_IDS]).toEqual(
      ['first_pullback', 'bull_flag', 'flat_top_breakout', 'flat_top_5m', 'red_to_green', 'gap_and_go',
        'pullback_dip', 'abcd', 'backside_lower_high', 'bear_flag', 'failed_breakout', 'lost_vwap', 'ssr_bounce',
        'micro_pullback']);
    for (const id of BOT_SETUP_IDS) {
      expect(BOT_SETUP_LABELS[id].length).toBeGreaterThan(3);
    }
  });
});
