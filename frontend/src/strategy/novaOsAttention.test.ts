/** Vitest: Nova OS attention mute + decision→kind mapping (no DOM Audio required). */
import { beforeEach, describe, expect, it } from 'vitest';
import {
  attentionKindForDecision,
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

  it('maps decide verdicts to attention kinds', () => {
    expect(attentionKindForDecision('BUY')).toBe('decision_buy');
    expect(attentionKindForDecision('WAIT')).toBe('decision_wait');
    expect(attentionKindForDecision('NO_BUY')).toBe('decision_no_buy');
  });

  it('persists mute preference and still records events', () => {
    setNovaOsAttentionMuted(true);
    expect(isNovaOsAttentionMuted()).toBe(true);
    let latest = 0;
    const unsub = subscribeNovaOsAttention((events) => {
      latest = events.length;
    });
    pushNovaOsAttention('decision_buy', { symbol: 'MOCK' });
    expect(latest).toBe(1);
    unsub();
  });
});
