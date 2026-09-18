import { describe, expect, it, vi } from 'vitest';
import {
  applyGpuPolicy,
  applyWin32PaintSwitches,
  mergeDisableFeatures,
  shouldDisableHardwareAcceleration,
  WIN32_DISABLE_FEATURES,
} from '../../electron/gpuPolicy.mjs';

describe('shouldDisableHardwareAcceleration', () => {
  it('defaults on for Windows and off elsewhere', () => {
    expect(shouldDisableHardwareAcceleration({}, 'win32')).toBe(true);
    expect(shouldDisableHardwareAcceleration({}, 'linux')).toBe(false);
    expect(shouldDisableHardwareAcceleration({}, 'darwin')).toBe(false);
  });

  it('NOVA_ELECTRON_GPU=1 keeps GPU on Windows', () => {
    expect(shouldDisableHardwareAcceleration({ NOVA_ELECTRON_GPU: '1' }, 'win32')).toBe(
      false,
    );
  });

  it('NOVA_ELECTRON_GPU=0 forces software on Linux', () => {
    expect(shouldDisableHardwareAcceleration({ NOVA_ELECTRON_GPU: '0' }, 'linux')).toBe(
      true,
    );
  });
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
  it('always applies Windows occlusion switches and software raster by default', () => {
    const app = {
      disableHardwareAcceleration: vi.fn(),
      commandLine: { appendSwitch: vi.fn(), getSwitchValue: () => '' },
    };
    expect(applyGpuPolicy(app, {}, 'win32')).toBe(true);
    expect(app.disableHardwareAcceleration).toHaveBeenCalledOnce();
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith(
      'disable-features',
      WIN32_DISABLE_FEATURES,
    );
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith(
      'disable-gpu-compositing',
    );
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith(
      'disable-direct-composition',
    );
  });

  it('keeps GPU on Windows when opted in, but still kills occlusion', () => {
    const app = {
      disableHardwareAcceleration: vi.fn(),
      commandLine: { appendSwitch: vi.fn(), getSwitchValue: () => '' },
    };
    expect(applyGpuPolicy(app, { NOVA_ELECTRON_GPU: '1' }, 'win32')).toBe(false);
    expect(app.disableHardwareAcceleration).not.toHaveBeenCalled();
    expect(app.commandLine.appendSwitch).toHaveBeenCalledWith(
      'disable-features',
      WIN32_DISABLE_FEATURES,
    );
    expect(app.commandLine.appendSwitch).not.toHaveBeenCalledWith(
      'disable-gpu-compositing',
    );
  });

  it('leaves GPU and occlusion switches alone on Linux by default', () => {
    const app = {
      disableHardwareAcceleration: vi.fn(),
      commandLine: { appendSwitch: vi.fn(), getSwitchValue: () => '' },
    };
    expect(applyGpuPolicy(app, {}, 'linux')).toBe(false);
    expect(app.disableHardwareAcceleration).not.toHaveBeenCalled();
    expect(app.commandLine.appendSwitch).not.toHaveBeenCalled();
  });
});
