/** Vitest: attention strip mute + event recording (no DOM Audio required). */
import { beforeEach, describe, expect, it } from 'vitest';
import {
  clearNovaOsAttention,
  isNovaOsAttentionMuted,
  pushNovaOsAttention,
  setNovaOsAttentionMuted,
  subscribeNovaOsAttention,
} from './novaOsAttention';

describe('novaOsAttention', () => {
  beforeEach(() => {
    clearNovaOsAttention();
    setNovaOsAttentionMuted(false);
  });

  it('persists mute preference and still records events', () => {
    setNovaOsAttentionMuted(true);
    expect(isNovaOsAttentionMuted()).toBe(true);
    let latest = 0;
    const unsub = subscribeNovaOsAttention((events) => {
      latest = events.length;
    });
    pushNovaOsAttention('kill');
    expect(latest).toBe(1);
    unsub();
  });
});
