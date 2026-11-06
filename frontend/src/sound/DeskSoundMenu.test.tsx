/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DESK_MUTE_REASON,
  DESK_SOUND_LEVEL_DEFAULTS,
  DESK_SOUND_LEVELS_KEY,
  DESK_STREAM_NOT_OPEN,
  DESK_STREAM_OFF_AIR,
} from './constants';
import { isDeskMuted, setDeskMuted } from './deskMute';
import { deskSoundLevel, deskSoundOn, resetDeskSoundsForTests, setDeskSoundLevel, setDeskSoundOn } from './deskSounds';
import { DeskSoundMenu } from './DeskSoundMenu';
import { resetStreamSoundForTests, setStreamPlayerState, wireStreamWindow } from './streamSound';
import { resetDeskTonesForTests } from './tones';

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

const row = (id: string) => screen.getByTestId(`desk-sound-row-${id}`);
const flip = (id: string) => screen.getByTestId(`desk-sound-switch-${id}`) as HTMLButtonElement;
const level = (id: string) => screen.getByTestId(`desk-sound-level-${id}`) as HTMLInputElement;
const play = (id: string) => screen.getByTestId(`desk-sound-play-${id}`) as HTMLButtonElement;

beforeEach(() => {
  localStorage.clear();
  start.mockClear();
  resetDeskSoundsForTests();
  resetDeskTonesForTests();
  resetStreamSoundForTests();
  vi.stubGlobal('AudioContext', FakeAudio);
});

afterEach(() => {
  cleanup();
  setDeskMuted(false);
  vi.unstubAllGlobals();
  delete (window as { novaDesktop?: unknown }).novaDesktop;
});

describe('DeskSoundMenu', () => {
  it('divides the sounds into the four sections', () => {
    render(<DeskSoundMenu id="m" />);
    const rows = (name: string) => within(screen.getByRole('region', { name })).getAllByRole('switch').map(s => s.getAttribute('aria-label'));
    expect(rows('Scanner')).toEqual(['HOD alerts', 'Setups']);
    expect(rows('Nine charts')).toEqual(['Moved up']);
    expect(rows('Trades')).toEqual(['Fill voice', 'Trader calls', 'Alarm']);
    expect(rows('YouTube')).toEqual(['TraderTV']);
  });

  it('every row shows its switch and its volume', () => {
    render(<DeskSoundMenu id="m" />);
    expect(flip('hod').getAttribute('aria-checked')).toBe('true');
    expect(level('hod').value).toBe(String(DESK_SOUND_LEVEL_DEFAULTS.hod));
    expect(flip('stream').getAttribute('aria-checked')).toBe('false');
    expect(level('stream').value).toBe(String(DESK_SOUND_LEVEL_DEFAULTS.stream));
  });

  it('a row\'s switch turns that sound alone off, and dims the row', () => {
    render(<DeskSoundMenu id="m" />);
    fireEvent.click(flip('hod'));
    expect(deskSoundOn('hod')).toBe(false);
    expect(deskSoundOn('setups')).toBe(true);
    expect(row('hod').className).toContain('is-dim');
    expect(row('setups').className).not.toContain('is-dim');
  });

  it('shows a change made elsewhere, as a source\'s own button makes', () => {
    render(<DeskSoundMenu id="m" />);
    act(() => setDeskSoundOn('setups', false));
    expect(flip('setups').getAttribute('aria-checked')).toBe('false');
    act(() => setDeskSoundLevel('setups', 66));
    expect(level('setups').value).toBe('66');
  });

  it('a slider sets the volume, and letting go plays the row once while it is on', () => {
    render(<DeskSoundMenu id="m" />);
    fireEvent.change(level('hod'), { target: { value: '70' } });
    expect(deskSoundLevel('hod')).toBe(70);
    expect(start).not.toHaveBeenCalled();
    fireEvent.pointerUp(level('hod'));
    expect(start).toHaveBeenCalledTimes(1);
    fireEvent.click(flip('hod'));
    fireEvent.pointerUp(level('hod'));
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('Play is heard with the row off', () => {
    render(<DeskSoundMenu id="m" />);
    fireEvent.click(flip('alarm'));
    fireEvent.click(play('alarm'));
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('All sounds is the header mute: the rows dim and keep what they were', () => {
    render(<DeskSoundMenu id="m" />);
    const all = screen.getByTestId('desk-sound-all');
    expect(all.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(flip('calls'));
    fireEvent.click(all);
    expect(isDeskMuted()).toBe(true);
    expect(all.getAttribute('aria-checked')).toBe('false');
    expect(row('hod').className).toContain('is-dim');
    expect(flip('hod').getAttribute('aria-checked')).toBe('true');
    fireEvent.click(all);
    expect(flip('hod').getAttribute('aria-checked')).toBe('true');
    expect(flip('calls').getAttribute('aria-checked')).toBe('false');
  });

  it('locks Play with its reason under the header mute and at volume 0', () => {
    render(<DeskSoundMenu id="m" />);
    expect(play('hod').disabled).toBe(false);
    act(() => setDeskMuted(true));
    expect(play('hod').disabled).toBe(true);
    expect(play('hod').getAttribute('data-why')).toBe(DESK_MUTE_REASON);
    act(() => setDeskMuted(false));
    fireEvent.change(level('hod'), { target: { value: '0' } });
    expect(play('hod').disabled).toBe(true);
    expect(play('hod').getAttribute('data-why')).toMatch(/volume is 0/);
  });
});

describe('the YouTube row', () => {
  it('is locked, saying why, with no player open and off air', () => {
    render(<DeskSoundMenu id="m" />);
    expect(flip('stream').disabled).toBe(true);
    expect(flip('stream').getAttribute('data-why')).toBe(DESK_STREAM_NOT_OPEN);
    expect(level('stream').disabled).toBe(true);
    expect(screen.queryByTestId('desk-sound-live')).toBeNull();
    act(() => setStreamPlayerState('offline'));
    expect(flip('stream').getAttribute('data-why')).toBe(DESK_STREAM_OFF_AIR);
  });

  it('turns on while the stream plays, and has no Play of its own', () => {
    render(<DeskSoundMenu id="m" />);
    act(() => setStreamPlayerState('live'));
    expect(screen.getByTestId('desk-sound-live').textContent).toBe('Live');
    expect(screen.queryByTestId('desk-sound-play-stream')).toBeNull();
    fireEvent.click(flip('stream'));
    expect(deskSoundOn('stream')).toBe(true);
    fireEvent.change(level('stream'), { target: { value: '35' } });
    expect(deskSoundLevel('stream')).toBe(35);
  });

  it('goes off with its player, and with the header mute, until it is asked for again', () => {
    render(<DeskSoundMenu id="m" />);
    act(() => setStreamPlayerState('live'));
    fireEvent.click(flip('stream'));
    act(() => setDeskMuted(true));
    expect(deskSoundOn('stream')).toBe(false);
    act(() => setDeskMuted(false));
    expect(deskSoundOn('stream')).toBe(false);
    fireEvent.click(flip('stream'));
    act(() => setStreamPlayerState('none'));
    expect(deskSoundOn('stream')).toBe(false);
    expect(flip('stream').disabled).toBe(true);
  });

  describe('on the desktop', () => {
    function desktop(state: { open: boolean; on: boolean } = { open: false, on: true }) {
      let tellOpen: (open: boolean) => void = () => undefined;
      let tellSwitch: (on: boolean) => void = () => undefined;
      const setStreamSound = vi.fn();
      (window as { novaDesktop?: unknown }).novaDesktop = {
        isDesktop: true,
        apiBase: '',
        setStreamSound,
        streamWindowState: async () => state,
        onStreamWindow: (cb: (open: boolean) => void) => {
          tellOpen = cb;
          return () => undefined;
        },
        onStreamSwitch: (cb: (on: boolean) => void) => {
          tellSwitch = cb;
          return () => undefined;
        },
      };
      const unwire = wireStreamWindow();
      return { open: (open: boolean) => tellOpen(open), otherPage: (on: boolean) => tellSwitch(on), setStreamSound, unwire };
    }

    it('drives the pop-out: on as it opens, off with the row, off when it closes', () => {
      const { open, setStreamSound, unwire } = desktop();
      render(<DeskSoundMenu id="m" />);
      act(() => open(true));
      expect(screen.getByTestId('desk-sound-live')).toBeTruthy();
      expect(flip('stream').disabled).toBe(false);
      expect(setStreamSound).toHaveBeenLastCalledWith({ on: true, level: DESK_SOUND_LEVEL_DEFAULTS.stream });
      fireEvent.click(flip('stream'));
      expect(setStreamSound).toHaveBeenLastCalledWith({ on: false, level: DESK_SOUND_LEVEL_DEFAULTS.stream });
      fireEvent.change(level('stream'), { target: { value: '20' } });
      expect(setStreamSound).toHaveBeenLastCalledWith({ on: false, level: 20 });
      fireEvent.click(flip('stream'));
      act(() => open(false));
      expect(deskSoundOn('stream')).toBe(false);
      expect(flip('stream').disabled).toBe(true);
      unwire();
    });

    it('a pop-out opened with the row already on still gets its volume, and so does the next stream in it', () => {
      const { open, setStreamSound, unwire } = desktop();
      render(<DeskSoundMenu id="m" />);
      act(() => setStreamPlayerState('live'));
      fireEvent.click(flip('stream'));
      fireEvent.change(level('stream'), { target: { value: '35' } });
      setStreamSound.mockClear();
      act(() => open(true));
      expect(setStreamSound).toHaveBeenCalledTimes(1);
      expect(setStreamSound).toHaveBeenLastCalledWith({ on: true, level: 35 });
      act(() => open(true));
      expect(setStreamSound).toHaveBeenCalledTimes(2);
      unwire();
    });

    it('follows the pop-out\'s switch moved in another page, and never sends an old one back', () => {
      const { open, otherPage, setStreamSound, unwire } = desktop();
      render(<DeskSoundMenu id="m" />);
      act(() => open(true));
      setStreamSound.mockClear();
      act(() => otherPage(false));
      expect(flip('stream').getAttribute('aria-checked')).toBe('false');
      expect(setStreamSound).not.toHaveBeenCalled();
      // That page's slider reaches this one through storage, and this one tells the desktop app too.
      act(() => {
        localStorage.setItem(DESK_SOUND_LEVELS_KEY, JSON.stringify({ schema_version: 1, value: { stream: 20 } }));
        window.dispatchEvent(new StorageEvent('storage', { key: DESK_SOUND_LEVELS_KEY }));
      });
      expect(setStreamSound).toHaveBeenCalledTimes(1);
      expect(setStreamSound).toHaveBeenLastCalledWith({ on: false, level: 20 });
      unwire();
    });

    it('with no pop-out open, another page\'s switch is not this page\'s', () => {
      const { otherPage, unwire } = desktop();
      render(<DeskSoundMenu id="m" />);
      act(() => setStreamPlayerState('live'));
      fireEvent.click(flip('stream'));
      act(() => otherPage(false));
      expect(deskSoundOn('stream')).toBe(true);
      unwire();
    });

    it('the header mute leaves the pop-out\'s row alone: it comes back with the desk', () => {
      const { open, unwire } = desktop();
      render(<DeskSoundMenu id="m" />);
      act(() => open(true));
      act(() => setDeskMuted(true));
      expect(deskSoundOn('stream')).toBe(true);
      unwire();
    });

    it('a page reloaded under an open pop-out picks up its state', async () => {
      const { unwire } = desktop({ open: true, on: false });
      render(<DeskSoundMenu id="m" />);
      await act(async () => {
        await Promise.resolve();
      });
      expect(flip('stream').disabled).toBe(false);
      expect(flip('stream').getAttribute('aria-checked')).toBe('false');
      unwire();
    });
  });
});
