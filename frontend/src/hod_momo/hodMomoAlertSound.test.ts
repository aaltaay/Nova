/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID } from '../constants';
import {
  evaluateHodMomoAlertPing,
  seedHodMomoSoundGate,
} from './hodMomoAlertSoundGate';
import {
  HOD_MOMO_ALERT_SOUND_COALESCE_MS,
  HOD_MOMO_ALERT_SOUND_KEY,
  isHodMomoAlertSoundOn,
  playHodMomoAlertPing,
  resetHodMomoAlertSoundForTests,
  setHodMomoAlertSoundOn,
} from './hodMomoAlertSound';

function hodAlert(id: string, ticker: string, strategy_id = 3) {
  return {
    id,
    ticker,
    timestamp: '2026-09-18T13:00:00Z',
    strategy_id,
  };
}

describe('hodMomoAlertSound gate', () => {
  beforeEach(() => {
    resetHodMomoAlertSoundForTests();
  });

  afterEach(() => {
    resetHodMomoAlertSoundForTests();
  });

  it('new HOD row pings when sound is on', () => {
    const seeded = seedHodMomoSoundGate([hodAlert('a1', 'OLD')]);
    const result = evaluateHodMomoAlertPing(
      seeded,
      [hodAlert('a2', 'NEW')],
      true,
    );
    expect(result.play).toBe(true);
  });

  it('muted desk never pings even on a new row', () => {
    const seeded = seedHodMomoSoundGate([]);
    const result = evaluateHodMomoAlertPing(
      seeded,
      [hodAlert('a1', 'AAPL')],
      false,
    );
    expect(result.play).toBe(false);
  });

  it('duplicate id / reconnect replay does not ping', () => {
    const replay = hodAlert('a1', 'AAPL');
    const seeded = seedHodMomoSoundGate([replay]);
    expect(evaluateHodMomoAlertPing(seeded, [replay], true).play).toBe(false);
    expect(
      evaluateHodMomoAlertPing(seeded, [{ ...replay, ticker: 'MSFT' }], true).play,
    ).toBe(false);
  });

  it('same ticker re-fire is not a new row', () => {
    const seeded = seedHodMomoSoundGate([hodAlert('a1', 'AAPL')]);
    const result = evaluateHodMomoAlertPing(
      seeded,
      [hodAlert('a2', 'AAPL')],
      true,
    );
    expect(result.play).toBe(false);
  });

  it('Running Up arrivals do not ping', () => {
    const seeded = seedHodMomoSoundGate([]);
    const result = evaluateHodMomoAlertPing(
      seeded,
      [hodAlert('ru1', 'MOMO', HOD_MOMO_RUNNING_UP_STRATEGY_ID)],
      true,
    );
    expect(result.play).toBe(false);
  });

  it('one burst of new HOD rows is a single play decision', () => {
    const seeded = seedHodMomoSoundGate([]);
    const result = evaluateHodMomoAlertPing(
      seeded,
      [hodAlert('a1', 'AAA'), hodAlert('a2', 'BBB'), hodAlert('a3', 'CCC')],
      true,
    );
    expect(result.play).toBe(true);
  });

  it('empty initial (clear today) then a new ticker pings', () => {
    const afterDay = seedHodMomoSoundGate([hodAlert('old', 'AAPL')]);
    const cleared = seedHodMomoSoundGate([]);
    expect(cleared.seenRows.size).toBe(0);
    expect(afterDay.seenRows.has('AAPL')).toBe(true);
    expect(
      evaluateHodMomoAlertPing(cleared, [hodAlert('new', 'AAPL')], true).play,
    ).toBe(true);
  });
});

describe('hodMomoAlertSound persist + play', () => {
  beforeEach(() => {
    resetHodMomoAlertSoundForTests();
  });

  afterEach(() => {
    resetHodMomoAlertSoundForTests();
    vi.unstubAllGlobals();
  });

  it('defaults on and survives reload via localStorage', () => {
    expect(isHodMomoAlertSoundOn()).toBe(true);
    setHodMomoAlertSoundOn(false);
    expect(localStorage.getItem(HOD_MOMO_ALERT_SOUND_KEY)).toBe('0');
    expect(isHodMomoAlertSoundOn()).toBe(false);
    setHodMomoAlertSoundOn(true);
    expect(localStorage.getItem(HOD_MOMO_ALERT_SOUND_KEY)).toBe('1');
  });

  it('playHodMomoAlertPing no-ops when muted', () => {
    setHodMomoAlertSoundOn(false);
    expect(playHodMomoAlertPing(1_000)).toBe(false);
  });

  it('coalesces a second play inside the burst window', () => {
    const start = ctxFactory();
    vi.stubGlobal('AudioContext', start.AudioContext);
    expect(playHodMomoAlertPing(10_000)).toBe(true);
    expect(playHodMomoAlertPing(10_000 + HOD_MOMO_ALERT_SOUND_COALESCE_MS - 1)).toBe(
      false,
    );
    expect(playHodMomoAlertPing(10_000 + HOD_MOMO_ALERT_SOUND_COALESCE_MS)).toBe(
      true,
    );
  });
});

function ctxFactory() {
  class FakeAudioContext {
    currentTime = 0;
    state = 'running';
    destination = {};
    resume = vi.fn();
    createOscillator() {
      return {
        connect: vi.fn(),
        start: vi.fn(),
        stop: vi.fn(),
        frequency: { value: 0 },
      };
    }
    createGain() {
      return {
        connect: vi.fn(),
        gain: { value: 0, exponentialRampToValueAtTime: vi.fn() },
      };
    }
  }
  return { AudioContext: FakeAudioContext };
}
