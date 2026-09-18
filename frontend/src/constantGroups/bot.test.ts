import { describe, expect, it } from 'vitest';
import {
  BOT_PACKS,
  BOT_PACK_DESCRIPTIONS,
  BOT_PACK_LLM_DECIDE,
  BOT_SYMBOL_ALLOWLIST_CAP,
  botAllowlistStripLabel,
  packDescription,
  packStatus,
  quoteSpikeSettingsLine,
  volumeSettingsLine,
} from './bot';

describe('bot pack copy', () => {
  it('has one sentence per pack id', () => {
    expect(BOT_PACKS).toContain(BOT_PACK_LLM_DECIDE);
    for (const id of BOT_PACKS) {
      const text = BOT_PACK_DESCRIPTIONS[id];
      expect(text.length).toBeGreaterThan(24);
      expect(text.includes('.')).toBe(true);
      expect(packDescription(id)).toBe(text);
    }
    expect(BOT_PACK_DESCRIPTIONS['halt-luld'].toLowerCase()).toMatch(/halt|luld/);
    expect(BOT_PACK_DESCRIPTIONS['quote-spike'].toLowerCase()).not.toMatch(/stub/);
    expect(BOT_PACK_DESCRIPTIONS['quote-spike'].toLowerCase()).toMatch(/3%|last|mid/);
    expect(BOT_PACK_DESCRIPTIONS.volume.toLowerCase()).not.toMatch(/stub/);
    expect(BOT_PACK_DESCRIPTIONS.volume.toLowerCase()).toMatch(/5x|day-volume|60/);
    expect(BOT_PACK_DESCRIPTIONS['llm-decide']).toMatch(/L2 \+ Activate/);
    expect(BOT_PACK_DESCRIPTIONS['llm-decide']).not.toMatch(/LLM_LIVE_FIRE/);
  });

  it('updates when the pack id changes', () => {
    expect(packDescription('halt-luld')).not.toBe(packDescription('llm-decide'));
    expect(packDescription('volume')).not.toBe(packDescription('quote-spike'));
    expect(packStatus('quote-spike')).toBe('live');
    expect(packStatus('volume')).toBe('live');
    expect(quoteSpikeSettingsLine({ min_pct: 3, window_sec: 5, spike_kind: 'buy_market', cooldown_sec: 30 }))
      .toMatch(/3% in 5s/);
    expect(volumeSettingsLine({
      min_mult: 5, window_sec: 60, baseline_sec: 600, volume_kind: 'buy_market', cooldown_sec: 60,
    })).toMatch(/5x/);
  });

  it('mirrors the backend symbol-allowlist cap and strip count label', () => {
    expect(BOT_SYMBOL_ALLOWLIST_CAP).toBe(50);
    expect(botAllowlistStripLabel(0)).toBe('Allowlist · 0');
    expect(botAllowlistStripLabel(3)).toBe('Allowlist · 3');
  });
});
