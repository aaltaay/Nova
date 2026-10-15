/** Vitest: attention strip mute + event recording (no DOM Audio required). */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setDeskMuted } from '../sound';
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

  it('the header mute silences the alarm; the strip still records it', () => {
    let tones = 0;
    vi.stubGlobal('AudioContext', class {
      currentTime = 0;
      destination = {};
      createOscillator() {
        tones += 1;
        return { connect() {}, frequency: { value: 0 }, start() {}, stop() {} };
      }
      createGain() {
        return { connect() {}, gain: { value: 0, exponentialRampToValueAtTime() {} } };
      }
    });
    let latest = 0;
    const unsub = subscribeNovaOsAttention((events) => {
      latest = events.length;
    });
    setDeskMuted(true);
    pushNovaOsAttention('kill');
    expect(tones).toBe(0);
    expect(latest).toBe(1);
    setDeskMuted(false);
    pushNovaOsAttention('kill');
    expect(tones).toBe(1);
    unsub();
    vi.unstubAllGlobals();
  });
});
