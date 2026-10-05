import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writeChoice } from '../../electron/graphicsChoice.mjs';
import {
  applyGpuPolicy,
  applyWin32PaintSwitches,
  mergeDisableFeatures,
  WIN32_DISABLE_FEATURES,
} from '../../electron/gpuPolicy.mjs';

function fakeApp() {
  return {
    disableHardwareAcceleration: vi.fn(),
    commandLine: { appendSwitch: vi.fn(), getSwitchValue: () => '' },
  };
}

let dir = '';
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-gpu-'));
});
afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

describe('mergeDisableFeatures', () => {
  it('keeps existing Chromium disable-features when adding occlusion', () => {
    expect(mergeDisableFeatures('Foo,Bar', WIN32_DISABLE_FEATURES)).toBe(
      `Foo,Bar,${WIN32_DISABLE_FEATURES}`,
    );
    expect(mergeDisableFeatures(WIN32_DISABLE_FEATURES, WIN32_DISABLE_FEATURES)).toBe(
      WIN32_DISABLE_FEATURES,
    );
  });
});

describe('applyWin32PaintSwitches', () => {
  it('disables occlusion tracking on Windows only', () => {
    const switches = new Map<string, string | true>();
    const app = {
      commandLine: {
        getSwitchValue: (name: string) =>
          typeof switches.get(name) === 'string' ? String(switches.get(name)) : '',
        appendSwitch: (name: string, value?: string) => {
          switches.set(name, value ?? true);
        },
      },
    };
    expect(applyWin32PaintSwitches(app, 'linux')).toBe(false);
    expect(applyWin32PaintSwitches(app, 'win32')).toBe(true);
    expect(switches.get('disable-features')).toBe(WIN32_DISABLE_FEATURES);
    expect(switches.get('disable-backgrounding-occluded-windows')).toBe(true);
  });
});

describe('applyGpuPolicy', () => {
  it('draws with the graphics card on Windows by default, and still kills occlusion', () => {
    const app = fakeApp();
    expect(applyGpuPolicy(app, {}, 'win32', dir)).toMatchObject({ gpu: true, source: 'default' });
    expect(app.disableHardwareAcceleration).not.toHaveBeenCalled();
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith('disable-features', WIN32_DISABLE_FEATURES);
    expect(app.commandLine.appendSwitch).not.toHaveBeenCalledWith('disable-gpu-compositing');
  });

  it('draws in software when the saved choice says so', () => {
    writeChoice(dir, { gpu: 'off', reason: 'blank_window', at: 1, detail: null, told: false });
    const app = fakeApp();
    expect(applyGpuPolicy(app, {}, 'win32', dir)).toMatchObject({ gpu: false, source: 'choice' });
    expect(app.disableHardwareAcceleration).toHaveBeenCalledOnce();
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith('disable-gpu-compositing');
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith('disable-direct-composition');
  });

  it('draws in software, and says so, when the saved choice cannot be read', () => {
    fs.writeFileSync(path.join(dir, 'graphics.json'), '{"schema_version": 7, "gpu": "on"}');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const app = fakeApp();
    expect(applyGpuPolicy(app, {}, 'win32', dir)).toMatchObject({ gpu: false, source: 'unreadable' });
    expect(app.disableHardwareAcceleration).toHaveBeenCalledOnce();
    expect(warn.mock.calls[0][0]).toMatch(/schema_version 7 is not 1; drawing in software/);
    warn.mockRestore();
  });

  it('lets NOVA_ELECTRON_GPU win over the saved choice', () => {
    writeChoice(dir, { gpu: 'on', reason: 'operator', at: 1, detail: null, told: true });
    const app = fakeApp();
    expect(applyGpuPolicy(app, { NOVA_ELECTRON_GPU: '0' }, 'win32', dir)).toMatchObject({ gpu: false, source: 'env' });
    expect(app.disableHardwareAcceleration).toHaveBeenCalledOnce();
  });

  it('leaves the occlusion switches alone on Linux', () => {
    const app = fakeApp();
    expect(applyGpuPolicy(app, {}, 'linux')).toMatchObject({ gpu: true });
    expect(app.disableHardwareAcceleration).not.toHaveBeenCalled();
    expect(app.commandLine.appendSwitch).not.toHaveBeenCalled();
  });
});
