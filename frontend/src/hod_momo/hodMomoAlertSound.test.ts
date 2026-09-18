/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_ALERT_SOUND_COALESCE_MS, HOD_MOMO_ALERT_SOUND_KEY } from './hodMomoAlertSoundConstants';
import {
  hodMomoAlertDedupeKey,
  isHodMomoAlertSoundEnabled,
  noteHodMomoLiveAlert,
  rememberHodMomoAlertSnapshot,
  resetHodMomoAlertSoundForTests,
  setHodMomoAlertSoundEnabled,
} from './hodMomoAlertSound';
import type { AlertObject } from './types';

const start = vi.fn();
const stop = vi.fn();
const ramp = vi.fn();

class FakeAudioContext {
  currentTime = 0;
  state = 'running';
  destination = {};
  resume = vi.fn();
  createOscillator() {
    return {
      connect: vi.fn(),
      frequency: { value: 0 },
      start,
      stop,
    };
  }
  createGain() {
    return {
      connect: vi.fn(),
      gain: { value: 0, exponentialRampToValueAtTime: ramp },
    };
  }
}

function alert(overrides: Partial<AlertObject> = {}): AlertObject {
  return {
    id: 'a-1',
    timestamp: '2026-09-18T10:00:00Z',
    ticker: 'ABCD',
    strategy_id: 7,
    strategy_name: 'Low Float - High Rel Vol',
    price: 4.2,
    change_pct: 12,
    rvol: 8,
    float_shares: 1_000_000,
    gap_pct: 9,
    volume: 200_000,
    momentum_pct: 5,
    rvol_source: 'ibkr',
    consolidation_count: 1,
    consolidated_ids: ['a-1'],
    ...overrides,
  };
}

describe('hodMomoAlertSound', () => {
  beforeEach(() => {
    localStorage.clear();
    start.mockClear();
    stop.mockClear();
    ramp.mockClear();
    vi.stubGlobal('AudioContext', FakeAudioContext);
    resetHodMomoAlertSoundForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    resetHodMomoAlertSoundForTests();
  });

  it('plays one ping for a new HOD row when sound is on', () => {
    expect(isHodMomoAlertSoundEnabled()).toBe(true);
    expect(noteHodMomoLiveAlert(alert(), 1_000)).toBe('pinged');
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('does not ping when the banner mute is on', () => {
    setHodMomoAlertSoundEnabled(false);
    expect(isHodMomoAlertSoundEnabled()).toBe(false);
    expect(noteHodMomoLiveAlert(alert(), 1_000)).toBe('muted');
    expect(start).not.toHaveBeenCalled();
  });

  it('does not ping a duplicate id or a reconnect snapshot replay', () => {
    const first = alert({ id: 'row-9', ticker: 'WXYZ' });
    expect(noteHodMomoLiveAlert(first, 1_000)).toBe('pinged');
    expect(start).toHaveBeenCalledTimes(1);

    expect(noteHodMomoLiveAlert(first, 2_000)).toBe('duplicate');
    expect(start).toHaveBeenCalledTimes(1);

    rememberHodMomoAlertSnapshot([first, alert({ id: 'row-10', ticker: 'EFGH' })]);
    expect(noteHodMomoLiveAlert(first, 3_000)).toBe('duplicate');
    expect(noteHodMomoLiveAlert(alert({ id: 'row-10', ticker: 'EFGH' }), 3_100)).toBe(
      'duplicate',
    );
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('dedupes a missing id by symbol+time and skips Running Up', () => {
    const noId = alert({ id: '  ', ticker: 'PING', timestamp: 't1' });
    expect(hodMomoAlertDedupeKey(noId)).toBe('sym:PING|t1');
    expect(noteHodMomoLiveAlert(noId, 1_000)).toBe('pinged');
    expect(noteHodMomoLiveAlert({ ...noId, strategy_id: 3 }, 2_000)).toBe('duplicate');

    expect(
      noteHodMomoLiveAlert(alert({ id: 'ru-1', strategy_id: 12, ticker: 'RUN' }), 3_000),
    ).toBe('running_up');
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('coalesces a burst to one ping and persists the banner pref', () => {
    expect(noteHodMomoLiveAlert(alert({ id: 'b1' }), 10_000)).toBe('pinged');
    expect(
      noteHodMomoLiveAlert(alert({ id: 'b2' }), 10_000 + HOD_MOMO_ALERT_SOUND_COALESCE_MS - 1),
    ).toBe('coalesced');
    expect(start).toHaveBeenCalledTimes(1);
    expect(
      noteHodMomoLiveAlert(alert({ id: 'b3' }), 10_000 + HOD_MOMO_ALERT_SOUND_COALESCE_MS),
    ).toBe('pinged');
    expect(start).toHaveBeenCalledTimes(2);

    setHodMomoAlertSoundEnabled(false);
    const stored = JSON.parse(localStorage.getItem(HOD_MOMO_ALERT_SOUND_KEY) ?? '');
    expect(stored.value).toBe(false);
    resetHodMomoAlertSoundForTests();
    expect(isHodMomoAlertSoundEnabled()).toBe(false);
  });
});
