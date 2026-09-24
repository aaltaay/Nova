/**
 * The "Starting Nova" window (startupSplash.mjs): on a cold start nothing of
 * Nova was on screen until the local engine answered and the desk loaded.
 * These pin what it says, where it opens, and that it goes away exactly when
 * the desk is on screen.
 */
import { EventEmitter } from 'node:events';
import { describe, expect, it, vi } from 'vitest';
import {
  STARTUP_SPLASH_HEIGHT,
  STARTUP_SPLASH_WIDTH,
  STARTUP_STEPS,
  engineStep,
  openStartupSplash,
  splashBounds,
  splashHtml,
} from '../../electron/startupSplash.mjs';

class FakeWindow extends EventEmitter {
  static last: FakeWindow | null = null;
  options: Record<string, unknown>;
  destroyed = false;
  visible = false;
  webContents = Object.assign(new EventEmitter(), {
    executeJavaScript: vi.fn(async () => undefined),
    setWindowOpenHandler: vi.fn(),
  });
  setBounds = vi.fn();
  loadURL = vi.fn(async () => undefined);
  constructor(options: Record<string, unknown> = {}) {
    super();
    this.options = options;
    FakeWindow.last = this;
  }
  show() {
    this.visible = true;
    this.emit('show');
  }
  destroy() {
    this.destroyed = true;
    this.emit('closed');
  }
  isDestroyed() {
    return this.destroyed;
  }
  isVisible() {
    return this.visible;
  }
}

const TARGET = { x: -2560, y: 0, width: 2560, height: 1400 };

function open() {
  const splash = openStartupSplash({ BrowserWindow: FakeWindow, target: TARGET, version: 'v976' });
  return { splash, win: FakeWindow.last as FakeWindow };
}

function writtenSteps(win: FakeWindow) {
  return win.webContents.executeJavaScript.mock.calls.map((call) => {
    const match = /textContent = (".*?");/.exec(String((call as unknown[])[0]));
    return match ? JSON.parse(match[1]) : null;
  });
}

describe('what the window says', () => {
  it('names the version and starts on looking for the engine, with no script of its own', () => {
    const html = splashHtml('v976');
    expect(html).toContain('Starting Nova v976');
    expect(html).toContain(STARTUP_STEPS.looking);
    expect(html).toContain("default-src 'none'");
    expect(html).not.toContain('<script');
  });

  it('escapes the version', () => {
    expect(splashHtml('<b>')).toContain('Starting Nova &#60;b&#62;');
  });

  it('says starting when Nova spawned the engine, connecting when one was already running', () => {
    expect(engineStep('spawned')).toBe(STARTUP_STEPS.starting);
    expect(engineStep('reused')).toBe(STARTUP_STEPS.connecting);
    expect(engineStep('attach')).toBe(STARTUP_STEPS.connecting);
    expect(engineStep('running')).toBe(STARTUP_STEPS.connecting);
  });
});

describe('where it opens', () => {
  it('centres on the rect the desk will open in', () => {
    expect(splashBounds(TARGET)).toEqual({
      x: -2560 + (2560 - STARTUP_SPLASH_WIDTH) / 2,
      y: (1400 - STARTUP_SPLASH_HEIGHT) / 2,
      width: STARTUP_SPLASH_WIDTH,
      height: STARTUP_SPLASH_HEIGHT,
    });
  });

  it('stays inside a rect smaller than itself', () => {
    const b = splashBounds({ x: 100, y: 50, width: 300, height: 100 });
    expect([b.x, b.y]).toEqual([100, 50]);
  });

  it('is placed with setBounds after creation, which lands exactly on a scaled display', () => {
    const { win } = open();
    expect(win.options.show).toBe(false);
    expect(win.setBounds).toHaveBeenCalledWith(splashBounds(TARGET));
  });
});

describe('openStartupSplash', () => {
  it('writes each step, and the latest again once the page has loaded', () => {
    const { splash, win } = open();
    splash.step(STARTUP_STEPS.starting);
    win.webContents.emit('did-finish-load');
    splash.step(STARTUP_STEPS.loading);
    expect(writtenSteps(win)).toEqual([STARTUP_STEPS.starting, STARTUP_STEPS.starting, STARTUP_STEPS.loading]);
  });

  it('shows itself when ready and closes the moment the desk shows', () => {
    const { splash, win } = open();
    win.emit('ready-to-show');
    expect(win.visible).toBe(true);
    const desk = new FakeWindow();
    splash.closeWhenShown(desk);
    expect(win.destroyed).toBe(false);
    desk.show();
    expect(win.destroyed).toBe(true);
    expect(splash.window).toBeNull();
  });

  it('closes at once when the desk is already visible, and when the desk is closed before it shows', () => {
    const first = open();
    const shown = new FakeWindow();
    shown.visible = true;
    first.splash.closeWhenShown(shown);
    expect(first.win.destroyed).toBe(true);

    const second = open();
    const desk = new FakeWindow();
    second.splash.closeWhenShown(desk);
    desk.destroy();
    expect(second.win.destroyed).toBe(true);
  });

  it("calls the launch off when the operator closes it, but not when Nova closes it", () => {
    const onCancel = vi.fn();
    const operator = openStartupSplash({ BrowserWindow: FakeWindow, target: TARGET, onCancel });
    (FakeWindow.last as FakeWindow).emit('close');
    expect(onCancel).toHaveBeenCalledTimes(1);

    const nova = openStartupSplash({ BrowserWindow: FakeWindow, target: TARGET, onCancel });
    nova.close(); // destroy(): 'closed' only, never 'close'
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(operator.window).not.toBeNull();
  });

  it('never throws: without a window Nova starts as before', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const Broken = function Broken() {
      throw new Error('no display');
    };
    const splash = openStartupSplash({ BrowserWindow: Broken, target: TARGET });
    expect(splash.window).toBeNull();
    expect(() => {
      splash.step(STARTUP_STEPS.loading);
      splash.closeWhenShown(new FakeWindow());
      splash.close();
    }).not.toThrow();
    error.mockRestore();
  });
});
