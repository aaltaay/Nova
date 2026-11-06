import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DESK_SOUND_CHANNEL,
  DESK_STREAM_SOUND_CHANNEL,
  DESK_STREAM_STATE_CHANNEL,
  DESK_STREAM_WINDOW_CHANNEL,
  announceStreamWindow,
  deskSoundMuted,
  resetDeskSoundForTests,
  streamVolumeScript,
  wireDeskSound,
} from '../../electron/deskSound.mjs';

type Handler = (event: unknown, ...args: unknown[]) => void;

function fakeWindow() {
  return { isDestroyed: () => false, webContents: { setAudioMuted: vi.fn() } };
}

function wire(windows: ReturnType<typeof fakeWindow>[]) {
  const ipc = new Map<string, Handler>();
  const appEvents = new Map<string, Handler>();
  wireDeskSound({
    ipcMain: { on: (ch: string, fn: Handler) => ipc.set(ch, fn), handle: vi.fn() },
    app: { on: (ev: string, fn: Handler) => appEvents.set(ev, fn) },
    BrowserWindow: { getAllWindows: () => windows },
  });
  return { send: (v: unknown) => ipc.get(DESK_SOUND_CHANNEL)?.({}, v), created: appEvents.get('browser-window-created') };
}

describe('deskSound', () => {
  beforeEach(() => resetDeskSoundForTests());

  it('mutes and unmutes every Nova window with the header switch', () => {
    const a = fakeWindow();
    const b = fakeWindow();
    const { send } = wire([a, b]);
    send(true);
    expect(deskSoundMuted()).toBe(true);
    expect(a.webContents.setAudioMuted).toHaveBeenLastCalledWith(true);
    expect(b.webContents.setAudioMuted).toHaveBeenLastCalledWith(true);
    send(false);
    expect(a.webContents.setAudioMuted).toHaveBeenLastCalledWith(false);
  });

  it('a window opened while muted starts muted (the stream pop-out)', () => {
    const { send, created } = wire([]);
    send(true);
    const stream = fakeWindow();
    created?.({}, stream);
    expect(stream.webContents.setAudioMuted).toHaveBeenCalledWith(true);
  });

  it('takes only a true as muted', () => {
    const { send } = wire([]);
    send('yes');
    expect(deskSoundMuted()).toBe(false);
  });
});

describe('the YouTube row on the pop-out', () => {
  beforeEach(() => resetDeskSoundForTests());

  function streamWindow() {
    return {
      isDestroyed: () => false,
      webContents: { setAudioMuted: vi.fn(), executeJavaScript: vi.fn(async () => undefined) },
    };
  }

  function wireStream(desk: ReturnType<typeof fakeWindow>, pop: ReturnType<typeof streamWindow> | null) {
    const ipc = new Map<string, Handler>();
    const handlers = new Map<string, () => unknown>();
    wireDeskSound({
      ipcMain: {
        on: (ch: string, fn: Handler) => ipc.set(ch, fn),
        handle: (ch: string, fn: () => unknown) => handlers.set(ch, fn),
      },
      app: { on: vi.fn() },
      BrowserWindow: { getAllWindows: () => (pop ? [desk, pop] : [desk]) },
      streamWindow: () => pop,
    });
    return {
      mute: (v: unknown) => ipc.get(DESK_SOUND_CHANNEL)?.({}, v),
      sound: (v: unknown) => ipc.get(DESK_STREAM_SOUND_CHANNEL)?.({}, v),
      state: () => handlers.get(DESK_STREAM_STATE_CHANNEL)?.(),
    };
  }

  it('mutes the pop-out alone, and asks its player for the volume', () => {
    const desk = fakeWindow();
    const pop = streamWindow();
    const { sound } = wireStream(desk, pop);
    sound({ on: false, level: 30 });
    expect(pop.webContents.setAudioMuted).toHaveBeenLastCalledWith(true);
    expect(desk.webContents.setAudioMuted).not.toHaveBeenCalled();
    expect(pop.webContents.executeJavaScript).toHaveBeenLastCalledWith(streamVolumeScript(30));
    sound({ on: true, level: 30 });
    expect(pop.webContents.setAudioMuted).toHaveBeenLastCalledWith(false);
  });

  it('the header mute holds the pop-out over the row, and it comes back with the desk', () => {
    const pop = streamWindow();
    const { mute, sound } = wireStream(fakeWindow(), pop);
    sound({ on: true, level: 50 });
    mute(true);
    expect(pop.webContents.setAudioMuted).toHaveBeenLastCalledWith(true);
    sound({ on: true, level: 60 });
    expect(pop.webContents.setAudioMuted).toHaveBeenLastCalledWith(true);
    mute(false);
    expect(pop.webContents.setAudioMuted).toHaveBeenLastCalledWith(false);
  });

  it('answers a reloaded page, and does nothing with no pop-out', () => {
    const { sound, state } = wireStream(fakeWindow(), null);
    expect(state()).toEqual({ open: false, on: true });
    expect(() => sound({ on: false, level: 20 })).not.toThrow();
    expect(state()).toEqual({ open: false, on: false });
  });

  it('builds the volume only from a number, clamped', () => {
    expect(streamVolumeScript(150)).toContain('setVolume(100)');
    expect(streamVolumeScript(-5)).toContain('setVolume(0)');
    expect(streamVolumeScript('1); alert(1')).toContain('setVolume(0)');
    expect(streamVolumeScript(25)).toContain('v.volume = 0.25');
  });

  it('tells every open page the pop-out opened or closed', () => {
    const send = vi.fn();
    const live = { isDestroyed: () => false, webContents: { send } };
    const gone = { isDestroyed: () => true, webContents: { send: vi.fn() } };
    announceStreamWindow({ getAllWindows: () => [live, gone] }, true);
    expect(send).toHaveBeenCalledWith(DESK_STREAM_WINDOW_CHANNEL, true);
    expect(gone.webContents.send).not.toHaveBeenCalled();
  });
});
