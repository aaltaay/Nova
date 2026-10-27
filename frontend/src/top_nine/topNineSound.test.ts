/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setDeskMuted } from '../sound';
import { TOP_NINE_CHIME_COOLDOWN_MS, TOP_NINE_CHIME_NOTES_HZ, TOP_NINE_HALT_NOTES_HZ } from './topNineConstants';
import { beepTopNineHalt, chimeTopNine, resetTopNineSoundForTests } from './topNineSound';

const start = vi.fn();

class FakeAudio {
  state = 'running';
  currentTime = 0;
  destination = {};
  createOscillator() {
    return { connect: vi.fn(), frequency: { value: 0 }, start, stop: vi.fn() };
  }
  createGain() {
    return { connect: vi.fn(), gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() } };
  }
}

describe('topNineSound', () => {
  beforeEach(() => {
    localStorage.clear();
    start.mockClear();
    resetTopNineSoundForTests();
    vi.stubGlobal('AudioContext', FakeAudio);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setDeskMuted(false);
  });

  it('chimes once, stays quiet for 30 s, then chimes again', () => {
    const t0 = 1_000_000;
    expect(chimeTopNine(true, t0)).toBe('played');
    expect(start).toHaveBeenCalledTimes(TOP_NINE_CHIME_NOTES_HZ.length);
    expect(chimeTopNine(true, t0 + 1_000)).toBe('cooldown');
    expect(chimeTopNine(true, t0 + TOP_NINE_CHIME_COOLDOWN_MS - 1)).toBe('cooldown');
    // A quiet switch inside the window is dropped, not queued: the window still runs from the first chime.
    expect(chimeTopNine(true, t0 + TOP_NINE_CHIME_COOLDOWN_MS)).toBe('played');
    expect(start).toHaveBeenCalledTimes(TOP_NINE_CHIME_NOTES_HZ.length * 2);
  });

  it('a muted chime starts no cooldown', () => {
    expect(chimeTopNine(false, 1_000)).toBe('muted');
    expect(chimeTopNine(true, 2_000)).toBe('played');
  });

  it('beeps for a halt even inside the chime cooldown', () => {
    expect(chimeTopNine(true, 1_000)).toBe('played');
    expect(beepTopNineHalt(true)).toBe('played');
    expect(start).toHaveBeenCalledTimes(TOP_NINE_CHIME_NOTES_HZ.length + TOP_NINE_HALT_NOTES_HZ.length);
  });

  it('the header mute silences both', () => {
    setDeskMuted(true);
    expect(chimeTopNine(true, 1_000)).toBe('muted');
    expect(beepTopNineHalt(true)).toBe('muted');
    expect(start).not.toHaveBeenCalled();
  });

  it('says so when the page has no audio', () => {
    vi.stubGlobal('AudioContext', undefined);
    expect(chimeTopNine(true, 1_000)).toBe('silent');
  });
});
