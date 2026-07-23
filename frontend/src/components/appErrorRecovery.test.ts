import { describe, expect, it } from 'vitest';
import {
  APP_SHELL_RELOAD_SESSION_KEY,
  clearShellAutoReloadSlot,
  consumeShellAutoReloadSlot,
  isFatalShellError,
} from './appErrorRecovery';

describe('appErrorRecovery', () => {
  it('flags provider / invalid-hook errors as fatal', () => {
    expect(
      isFatalShellError(new Error('useWorkspace must be used within WorkspaceProvider')),
    ).toBe(true);
    expect(isFatalShellError(new Error('Invalid hook call'))).toBe(true);
    expect(isFatalShellError(new Error('chart boom'))).toBe(false);
  });

  it('allows one auto-reload slot per session storage', () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
    } as Storage;

    expect(consumeShellAutoReloadSlot(storage)).toBe(true);
    expect(store.get(APP_SHELL_RELOAD_SESSION_KEY)).toBe('1');
    expect(consumeShellAutoReloadSlot(storage)).toBe(false);
    clearShellAutoReloadSlot(storage);
    expect(consumeShellAutoReloadSlot(storage)).toBe(true);
  });
});
