import { describe, expect, it } from 'vitest';
import {
  BOT_GATE_LABELS,
  BOT_SETUP_BLURBS,
  BOT_SETUP_IDS,
  BOT_SETUP_LABELS,
  BOT_SETUP_RESEARCH,
  BOT_SYMBOL_ALLOWLIST_CAP,
  botAllowlistStripLabel,
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

  it('labels every gate backend/bot/gates.py returns', () => {
    expect(Object.keys(BOT_GATE_LABELS).sort()).toEqual(
      ['allowlist', 'bot_trip', 'commissions', 'day_lock', 'depth_lines', 'desk_armed', 'kill_switch', 'level', 'readout', 'window'],
    );
  });

  it('mirrors the backend symbol-allowlist cap and strip count label', () => {
    expect(BOT_SYMBOL_ALLOWLIST_CAP).toBe(50);
    expect(botAllowlistStripLabel(0)).toBe('Allowlist · 0');
    expect(botAllowlistStripLabel(3)).toBe('Allowlist · 3');
  });
});
