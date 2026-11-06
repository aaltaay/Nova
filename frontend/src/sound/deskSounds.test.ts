/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DESK_SOUND_IDS,
  DESK_SOUND_KEYS,
  DESK_SOUND_LEVEL_DEFAULTS,
  DESK_SOUND_LEVELS_KEY,
  DESK_TONE_HOD,
  DESK_TONE_TOP_NINE_CHIME,
} from './constants';
import { setDeskMuted } from './deskMute';
import {
  deskSoundAudible,
  deskSoundGain,
  deskSoundLevel,
  deskSoundOn,
  resetDeskSoundsForTests,
  setDeskSoundLevel,
  setDeskSoundOn,
  subscribeDeskSounds,
} from './deskSounds';
import { playDeskTone, previewDeskSound, resetDeskTonesForTests } from './tones';

function fromAnotherWindow(key: string, value: string) {
  localStorage.setItem(key, value);
  window.dispatchEvent(new StorageEvent('storage', { key }));
}

beforeEach(() => {
  localStorage.clear();
  resetDeskSoundsForTests();
  resetDeskTonesForTests();
});

afterEach(() => {
  setDeskMuted(false);
  vi.unstubAllGlobals();
});

describe('each sound\'s switch', () => {
  it('starts on, but the stream, which never starts talking on its own', () => {
    for (const id of DESK_SOUND_IDS) expect(deskSoundOn(id)).toBe(id !== 'stream');
  });

  it('keeps each switch in the key and shape it always had', () => {
    setDeskSoundOn('hod', false);
    expect(JSON.parse(localStorage.getItem(DESK_SOUND_KEYS.hod) ?? 'null')).toEqual({ schema_version: 1, value: false });
    setDeskSoundOn('topNine', false);
    expect(JSON.parse(localStorage.getItem(DESK_SOUND_KEYS.topNine) ?? 'null')).toEqual({ schema_version: 1, value: false });
    setDeskSoundOn('calls', false);
    expect(JSON.parse(localStorage.getItem(DESK_SOUND_KEYS.calls) ?? 'null')).toEqual({ schema_version: 1, value: false });
    setDeskSoundOn('setups', false);
    expect(localStorage.getItem(DESK_SOUND_KEYS.setups)).toBe('off');
    setDeskSoundOn('alarm', false);
    expect(localStorage.getItem(DESK_SOUND_KEYS.alarm)).toBe('1'); // stored the other way round
    setDeskSoundOn('alarm', true);
    expect(localStorage.getItem(DESK_SOUND_KEYS.alarm)).toBe('0');
  });

  it('reads what an older desk stored', () => {
    localStorage.setItem(DESK_SOUND_KEYS.hod, JSON.stringify({ schema_version: 1, value: false }));
    localStorage.setItem(DESK_SOUND_KEYS.setups, 'off');
    localStorage.setItem(DESK_SOUND_KEYS.alarm, 'true');
    resetDeskSoundsForTests();
    expect(deskSoundOn('hod')).toBe(false);
    expect(deskSoundOn('setups')).toBe(false);
    expect(deskSoundOn('alarm')).toBe(false);
  });

  it('never stores the stream\'s', () => {
    setDeskSoundOn('stream', true);
    expect(deskSoundOn('stream')).toBe(true);
    expect(localStorage.length).toBe(0);
    resetDeskSoundsForTests();
    expect(deskSoundOn('stream')).toBe(false);
  });

  it('follows a switch moved in another window, and tells who listens', () => {
    const heard = vi.fn();
    const off = subscribeDeskSounds(heard);
    fromAnotherWindow(DESK_SOUND_KEYS.topNine, JSON.stringify({ schema_version: 1, value: false }));
    expect(deskSoundOn('topNine')).toBe(false);
    expect(heard).toHaveBeenCalledTimes(1);
    off();
  });
});

describe('each sound\'s volume', () => {
  it('starts at the level the desk always played', () => {
    for (const id of DESK_SOUND_IDS) expect(deskSoundLevel(id)).toBe(DESK_SOUND_LEVEL_DEFAULTS[id]);
    expect(deskSoundGain('hod', DESK_TONE_HOD.gain)).toBeCloseTo(DESK_TONE_HOD.gain);
    expect(deskSoundGain('topNine', DESK_TONE_TOP_NINE_CHIME.gain)).toBeCloseTo(DESK_TONE_TOP_NINE_CHIME.gain);
  });

  it('scales a tone from there: the top of the HOD slider is as loud as the desk\'s loudest', () => {
    setDeskSoundLevel('hod', 100);
    expect(deskSoundGain('hod', DESK_TONE_HOD.gain)).toBeCloseTo(0.22, 1);
  });

  it('stores one whole number per sound, clamped, and another window follows', () => {
    setDeskSoundLevel('hod', 60.4);
    setDeskSoundLevel('setups', 400);
    setDeskSoundLevel('calls', -3);
    expect(deskSoundLevel('hod')).toBe(60);
    expect(deskSoundLevel('setups')).toBe(100);
    expect(deskSoundLevel('calls')).toBe(0);
    const stored = JSON.parse(localStorage.getItem(DESK_SOUND_LEVELS_KEY) ?? 'null');
    expect(stored.schema_version).toBe(1);
    expect(stored.value.hod).toBe(60);
    fromAnotherWindow(DESK_SOUND_LEVELS_KEY, JSON.stringify({ schema_version: 1, value: { hod: 12 } }));
    expect(deskSoundLevel('hod')).toBe(12);
  });

  it('reads a bad entry or an unknown version as the default', () => {
    localStorage.setItem(DESK_SOUND_LEVELS_KEY, JSON.stringify({ schema_version: 1, value: { hod: 'loud', setups: 500, calls: 40 } }));
    resetDeskSoundsForTests();
    expect(deskSoundLevel('hod')).toBe(DESK_SOUND_LEVEL_DEFAULTS.hod);
    expect(deskSoundLevel('setups')).toBe(DESK_SOUND_LEVEL_DEFAULTS.setups);
    expect(deskSoundLevel('calls')).toBe(40);
    localStorage.setItem(DESK_SOUND_LEVELS_KEY, JSON.stringify({ schema_version: 99, value: { calls: 40 } }));
    resetDeskSoundsForTests();
    expect(deskSoundLevel('calls')).toBe(DESK_SOUND_LEVEL_DEFAULTS.calls);
  });
});

describe('deskSoundAudible', () => {
  it('needs the switch, a volume and no header mute', () => {
    expect(deskSoundAudible('hod')).toBe(true);
    setDeskSoundOn('hod', false);
    expect(deskSoundAudible('hod')).toBe(false);
    setDeskSoundOn('hod', true);
    setDeskSoundLevel('hod', 0);
    expect(deskSoundAudible('hod')).toBe(false);
    setDeskSoundLevel('hod', 10);
    setDeskMuted(true);
    expect(deskSoundAudible('hod')).toBe(false);
  });
});

describe('the one player', () => {
  function fakeAudio() {
    const peaks: number[] = [];
    const tones: number[] = [];
    vi.stubGlobal('AudioContext', class {
      state = 'running';
      currentTime = 0;
      destination = {};
      createOscillator() {
        const osc = { connect: vi.fn(), frequency: { value: 0 }, start: () => tones.push(osc.frequency.value), stop: vi.fn() };
        return osc;
      }
      createGain() {
        return { connect: vi.fn(), gain: { setValueAtTime: (v: number) => peaks.push(v), exponentialRampToValueAtTime: vi.fn() } };
      }
    });
    return { peaks, tones };
  }

  it('plays a tone at the sound\'s volume', () => {
    const { peaks, tones } = fakeAudio();
    expect(playDeskTone('topNine', DESK_TONE_TOP_NINE_CHIME)).toBe(true);
    expect(tones).toEqual([880, 1_320]);
    expect(peaks[0]).toBeCloseTo(0.2);
    setDeskSoundLevel('topNine', 45);
    playDeskTone('topNine', DESK_TONE_TOP_NINE_CHIME);
    expect(peaks[2]).toBeCloseTo(0.2 * 45 / 91);
  });

  it('Play is the sound itself, heard with the row off, never under the header mute', () => {
    const { tones } = fakeAudio();
    setDeskSoundOn('hod', false);
    expect(previewDeskSound('hod')).toBe(true);
    expect(tones).toEqual([880]);
    setDeskMuted(true);
    expect(previewDeskSound('hod')).toBe(false);
    expect(tones).toHaveLength(1);
  });

  it('has no Play for the stream, and says so with no audio in the page', () => {
    fakeAudio();
    expect(previewDeskSound('stream')).toBe(false);
    resetDeskTonesForTests();
    vi.stubGlobal('AudioContext', undefined);
    expect(playDeskTone('hod', DESK_TONE_HOD)).toBe(false);
  });
});
