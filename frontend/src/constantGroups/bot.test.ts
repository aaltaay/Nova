import { describe, expect, it } from 'vitest';
import {
  BOT_PACKS,
  BOT_PACK_DESCRIPTIONS,
  BOT_PACK_LLM_DECIDE,
  packDescription,
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
    expect(BOT_PACK_DESCRIPTIONS['quote-spike'].toLowerCase()).toMatch(/stub/);
    expect(BOT_PACK_DESCRIPTIONS.volume.toLowerCase()).toMatch(/stub/);
    expect(BOT_PACK_DESCRIPTIONS['llm-decide']).toMatch(/L2 \+ Activate/);
    expect(BOT_PACK_DESCRIPTIONS['llm-decide']).not.toMatch(/LLM_LIVE_FIRE/);
  });

  it('updates when the pack id changes', () => {
    expect(packDescription('halt-luld')).not.toBe(packDescription('llm-decide'));
    expect(packDescription('volume')).not.toBe(packDescription('quote-spike'));
  });
});
