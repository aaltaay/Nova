/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setDeskMuted } from '../sound';
import { pingCall, resetStockReadSoundForTests } from './whoTradesSound';

class FakeAudio {
  state = 'running';
  currentTime = 0;
  destination = {};
  createOscillator() {
    return { connect: vi.fn(), frequency: { value: 0 }, start: vi.fn(), stop: vi.fn() };
  }
  createGain() {
    return { connect: vi.fn(), gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() } };
  }
}

describe('whoTradesSound', () => {
  beforeEach(() => {
    localStorage.clear();
    resetStockReadSoundForTests();
    vi.stubGlobal('AudioContext', FakeAudio);
  });
  afterEach(() => {
    setDeskMuted(false);
    vi.unstubAllGlobals();
  });

  it('pings a call once', () => {
    expect(pingCall('c1', 'go')).toBe('pinged');
    expect(pingCall('c1', 'go')).toBe('duplicate');
  });

  it('stays quiet while the header mute is on, under its own switch', () => {
    setDeskMuted(true);
    expect(pingCall('c2', 'go')).toBe('muted');
  });
});
