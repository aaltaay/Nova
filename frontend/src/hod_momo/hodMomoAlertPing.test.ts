/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  HOD_MOMO_ALERT_PING_COALESCE_MS,
  HOD_MOMO_ALERT_SOUND_STORAGE_KEY,
  hydrateHodMomoAlertSoundFromStorage,
  ingestHodMomoAlertArrivals,
  ingestHodMomoAlertSnapshot,
  isHodMomoAlertSoundOn,
  playHodMomoAlertTone,
  resetHodMomoAlertPingForTests,
  setHodMomoAlertSoundOn,
} from './hodMomoAlertPing';
import type { HodAlertPingArrival } from './hodMomoAlertPing';

function alert(
  partial: Partial<HodAlertPingArrival> & Pick<HodAlertPingArrival, 'id' | 'ticker'>,
): HodAlertPingArrival {
  return {
    timestamp: '2026-09-18T13:00:00.000Z',
    strategy_id: 7,
    ...partial,
  };
}

function stubAudio() {
  const osc = {
    connect: vi.fn(),
    frequency: { value: 0 },
    start: vi.fn(),
    stop: vi.fn(),
  };
  const gain = {
    connect: vi.fn(),
    gain: { value: 0, exponentialRampToValueAtTime: vi.fn() },
  };
  class FakeAudioContext {
    destination = {};
    currentTime = 0;
    resume = vi.fn();
    createOscillator() {
      return osc;
    }
    createGain() {
      return gain;
    }
  }
  vi.stubGlobal('AudioContext', FakeAudioContext);
  return { osc, gain };
}

describe('hodMomoAlertPing', () => {
  beforeEach(() => {
    resetHodMomoAlertPingForTests();
    vi.useFakeTimers();
  });

  afterEach(() => {
    resetHodMomoAlertPingForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('pings once when a new HOD row arrives and sound is on', () => {
    const { osc } = stubAudio();
    const play = ingestHodMomoAlertArrivals([
      alert({ id: 'a1', ticker: 'ABCD' }),
    ]);
    expect(play).toBe(true);
    vi.advanceTimersByTime(HOD_MOMO_ALERT_PING_COALESCE_MS);
    expect(osc.start).toHaveBeenCalledTimes(1);
  });

  it('does not ping when the banner mute is on', () => {
    const { osc } = stubAudio();
    setHodMomoAlertSoundOn(false);
    const play = ingestHodMomoAlertArrivals([
      alert({ id: 'a1', ticker: 'ABCD' }),
    ]);
    expect(play).toBe(false);
    vi.advanceTimersByTime(HOD_MOMO_ALERT_PING_COALESCE_MS);
    expect(osc.start).not.toHaveBeenCalled();
  });

  it('does not ping a duplicate id or reconnect replay', () => {
    const { osc } = stubAudio();
    ingestHodMomoAlertSnapshot([
      alert({ id: 'a1', ticker: 'ABCD' }),
    ]);
    expect(
      ingestHodMomoAlertArrivals([alert({ id: 'a1', ticker: 'ABCD' })]),
    ).toBe(false);
    expect(
      ingestHodMomoAlertArrivals([
        alert({
          id: 'a-new-id',
          ticker: 'ABCD',
          timestamp: '2026-09-18T13:00:00.000Z',
        }),
      ]),
    ).toBe(false);
    vi.advanceTimersByTime(HOD_MOMO_ALERT_PING_COALESCE_MS);
    expect(osc.start).not.toHaveBeenCalled();
  });

  it('does not ping a later fire of a ticker already on the list', () => {
    ingestHodMomoAlertSnapshot([
      alert({ id: 'a1', ticker: 'ABCD', timestamp: '2026-09-18T13:00:00.000Z' }),
    ]);
    expect(
      ingestHodMomoAlertArrivals([
        alert({
          id: 'a2',
          ticker: 'ABCD',
          timestamp: '2026-09-18T13:05:00.000Z',
        }),
      ]),
    ).toBe(false);
  });

  it('does not ping Running Up arrivals on the shared stream', () => {
    expect(
      ingestHodMomoAlertArrivals([
        alert({ id: 'ru1', ticker: 'RUUP', strategy_id: 12 }),
      ]),
    ).toBe(false);
  });

  it('coalesces a burst of new rows into one ping', () => {
    const { osc } = stubAudio();
    expect(
      ingestHodMomoAlertArrivals([
        alert({ id: 'a1', ticker: 'AAAA' }),
        alert({ id: 'a2', ticker: 'BBBB' }),
        alert({ id: 'a3', ticker: 'CCCC' }),
      ]),
    ).toBe(true);
    vi.advanceTimersByTime(HOD_MOMO_ALERT_PING_COALESCE_MS);
    expect(osc.start).toHaveBeenCalledTimes(1);
  });

  it('persists the banner preference across a reload hydrate', () => {
    setHodMomoAlertSoundOn(false);
    expect(localStorage.getItem(HOD_MOMO_ALERT_SOUND_STORAGE_KEY)).toBe('0');
    expect(isHodMomoAlertSoundOn()).toBe(false);
    setHodMomoAlertSoundOn(true);
    expect(localStorage.getItem(HOD_MOMO_ALERT_SOUND_STORAGE_KEY)).toBe('1');
    setHodMomoAlertSoundOn(false);
    expect(hydrateHodMomoAlertSoundFromStorage()).toBe(false);
    expect(isHodMomoAlertSoundOn()).toBe(false);
  });

  it('playHodMomoAlertTone is a no-op while muted', () => {
    const { osc } = stubAudio();
    setHodMomoAlertSoundOn(false);
    playHodMomoAlertTone();
    expect(osc.start).not.toHaveBeenCalled();
  });
});
