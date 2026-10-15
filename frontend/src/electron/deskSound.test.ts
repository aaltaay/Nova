import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DESK_SOUND_CHANNEL,
  deskSoundMuted,
  resetDeskSoundForTests,
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
    ipcMain: { on: (ch: string, fn: Handler) => ipc.set(ch, fn) },
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
