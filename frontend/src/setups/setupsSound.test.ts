/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SETUPS_SOUND_STORAGE_KEY } from '../constants';
import {
  isSetupsSoundEnabled,
  noteSetupProposal,
  resetSetupsSoundForTests,
  setSetupsSoundEnabled,
  subscribeSetupsSound,
} from './setupsSound';

describe('setupsSound', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetSetupsSoundForTests();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('rings once per proposal id', () => {
    const start = vi.fn();
    const stop = vi.fn();
    class FakeAudio {
      state = 'running';
      currentTime = 0;
      destination = {};
      createOscillator() {
        return { connect: vi.fn(), frequency: { value: 0 }, start, stop };
      }
      createGain() {
        return { connect: vi.fn(), gain: { value: 0, exponentialRampToValueAtTime: vi.fn() } };
      }
    }
    vi.stubGlobal('AudioContext', FakeAudio);
    expect(noteSetupProposal('p1')).toBe('pinged');
    expect(noteSetupProposal('p1')).toBe('duplicate');
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('says so when the page has no audio', () => {
    vi.stubGlobal('AudioContext', undefined);
    expect(noteSetupProposal('p2')).toBe('silent');
  });

  it('stays quiet when muted, remembers the switch and tells subscribers', () => {
    const seen: boolean[] = [];
    const off = subscribeSetupsSound(v => seen.push(v));
    setSetupsSoundEnabled(false);
    expect(isSetupsSoundEnabled()).toBe(false);
    expect(window.localStorage.getItem(SETUPS_SOUND_STORAGE_KEY)).toBe('off');
    expect(noteSetupProposal('p3')).toBe('muted');
    off();
    setSetupsSoundEnabled(true);
    expect(seen).toEqual([false]);
  });
});
