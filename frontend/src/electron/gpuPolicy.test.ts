import { describe, expect, it, vi } from 'vitest';
import {
  applyGpuPolicy,
  shouldDisableHardwareAcceleration,
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

describe('applyGpuPolicy', () => {
  it('calls disableHardwareAcceleration on Windows', () => {
    const app = { disableHardwareAcceleration: vi.fn() };
    expect(applyGpuPolicy(app, {}, 'win32')).toBe(true);
    expect(app.disableHardwareAcceleration).toHaveBeenCalledOnce();
  });

  it('leaves GPU alone on Linux by default', () => {
    const app = { disableHardwareAcceleration: vi.fn() };
    expect(applyGpuPolicy(app, {}, 'linux')).toBe(false);
    expect(app.disableHardwareAcceleration).not.toHaveBeenCalled();
  });
});
