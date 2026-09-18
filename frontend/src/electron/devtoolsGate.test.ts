import { describe, expect, it } from 'vitest';
import { shouldOpenDetachedDevTools } from '../../electron/devtoolsGate.mjs';

describe('shouldOpenDetachedDevTools', () => {
  it('stays off for packaged builds even if the env is set', () => {
    expect(shouldOpenDetachedDevTools(false, { NOVA_ELECTRON_DEVTOOLS: '1' })).toBe(false);
  });

  it('stays off on the daily Electron→Vite path unless the flag is set', () => {
    expect(shouldOpenDetachedDevTools(true, {})).toBe(false);
    expect(shouldOpenDetachedDevTools(true, { NOVA_ELECTRON_DEVTOOLS: '' })).toBe(false);
    expect(shouldOpenDetachedDevTools(true, { NOVA_ELECTRON_DEVTOOLS: '0' })).toBe(false);
  });

  it('opens detach DevTools only when the env flag is on in unpackaged Electron', () => {
    expect(shouldOpenDetachedDevTools(true, { NOVA_ELECTRON_DEVTOOLS: '1' })).toBe(true);
    expect(shouldOpenDetachedDevTools(true, { NOVA_ELECTRON_DEVTOOLS: 'YES' })).toBe(true);
  });
});
