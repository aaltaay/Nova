/**
 * Only the main window hears the update notice and may answer it, and it
 * counts as listening only until it navigates (a reload, an error page).
 */
import { describe, expect, it, vi } from 'vitest';
import {
  UPDATE_ACT_CHANNEL,
  UPDATE_SUBSCRIBE_CHANNEL,
  UPDATE_VIEW_CHANNEL,
  createUpdateBridge,
} from '../../electron/updateBridge.mjs';

type Handler = (event: { sender: unknown }, request?: unknown) => unknown;

function contents() {
  const events: Record<string, () => void> = {};
  return {
    send: vi.fn(),
    on: vi.fn((name: string, fn: () => void) => {
      events[name] = fn;
    }),
    isDestroyed: () => false,
    fire: (name: string) => events[name]?.(),
  };
}

function setup() {
  const handlers: Record<string, Handler> = {};
  const main = contents();
  const win = { isDestroyed: () => false, webContents: main };
  const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn() };
  const bridge = createUpdateBridge({
    ipcMain: { handle: (channel: string, fn: Handler) => void (handlers[channel] = fn) },
    getWindow: () => win,
    logger,
  });
  return { bridge, main, logger, subscribe: handlers[UPDATE_SUBSCRIBE_CHANNEL], act: handlers[UPDATE_ACT_CHANNEL] };
}

describe('update bridge', () => {
  it('answers a subscribe with the view, then pushes each change once', () => {
    const { bridge, main, subscribe } = setup();
    bridge.set('installed', 'v975');
    expect(bridge.hasListener()).toBe(false);
    expect(subscribe({ sender: main })).toMatchObject({ schema_version: 1, installed: 'v975', notice: null });
    expect(bridge.hasListener()).toBe(true);
    bridge.set('notice', { stage: 'available', tag: 'v976' });
    bridge.set('notice', { stage: 'available', tag: 'v976' }); // unchanged: not re-sent
    expect(main.send).toHaveBeenCalledTimes(1);
    expect(main.send).toHaveBeenCalledWith(UPDATE_VIEW_CHANNEL, expect.objectContaining({ notice: { stage: 'available', tag: 'v976' } }));
  });

  it('stops counting a page that navigated away until it subscribes again', () => {
    const { bridge, main, subscribe } = setup();
    subscribe({ sender: main });
    main.fire('did-navigate');
    expect(bridge.hasListener()).toBe(false);
    bridge.set('notice', { stage: 'ready', tag: 'v976' });
    expect(main.send).not.toHaveBeenCalled();
    subscribe({ sender: main });
    expect(bridge.hasListener()).toBe(true);
  });

  it('refuses a Trader pop-out, and an action nobody handles', async () => {
    const { bridge, subscribe, act } = setup();
    const popout = contents();
    const download = vi.fn();
    bridge.on('download', download);
    expect(subscribe({ sender: popout })).toBeNull();
    expect(await act({ sender: popout }, { action: 'download' })).toMatchObject({ ok: false });
    expect(download).not.toHaveBeenCalled();
  });

  it('runs an answer without waiting on it, and logs one that fails', async () => {
    const { bridge, main, act, logger } = setup();
    bridge.on('download', () => new Promise(() => {})); // a download runs for minutes
    expect(await act({ sender: main }, { action: 'download' })).toEqual({ ok: true });
    bridge.on('restart', async () => {
      throw new Error('engine did not stop');
    });
    await act({ sender: main }, { action: 'restart' });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(logger.error).toHaveBeenCalledWith('update action restart failed: engine did not stop');
    expect(await act({ sender: main }, { action: 'format-disk' })).toMatchObject({ ok: false });
  });
});
