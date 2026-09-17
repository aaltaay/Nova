import { describe, expect, it } from 'vitest';
import {
  canExtractFromDesk,
  claimDockTarget,
  closePolicyAfterGive,
  deskRoleFromStockView,
  isForeignTabDrag,
  readLastHostWindow,
  rememberLastHostWindow,
  shouldHandleDockRequest,
} from './commands';

describe('trader desk commands', () => {
  it('closes a float window when it gives away its last tab', () => {
    expect(closePolicyAfterGive('float', 0)).toBe('close-window');
    expect(closePolicyAfterGive('float', 1)).toBe('keep');
    expect(closePolicyAfterGive('host', 0)).toBe('leave-scanner');
    expect(closePolicyAfterGive('host', 2)).toBe('keep');
  });

  it('treats a stock-view URL as a float surface', () => {
    expect(deskRoleFromStockView('IPST')).toBe('float');
    expect(deskRoleFromStockView(null)).toBe('host');
  });

  it('allows Pop out only on the host desk', () => {
    expect(canExtractFromDesk('host')).toBe(true);
    expect(canExtractFromDesk('float')).toBe(false);
  });

  it('ignores a drag that originated in this window', () => {
    expect(isForeignTabDrag('win-a', 'win-b')).toBe(true);
    expect(isForeignTabDrag('win-a', 'win-a')).toBe(false);
  });

  it('remembers the last host for Dock-button targeting', () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
    };
    expect(readLastHostWindow(storage)).toBeNull();
    rememberLastHostWindow(storage, 'host-1');
    expect(readLastHostWindow(storage)).toBe('host-1');
  });

  it('ignores a dock-request that still carries the host window id', () => {
    expect(shouldHandleDockRequest({
      role: 'host',
      sourceWindowId: 'host-1',
      thisWindowId: 'host-1',
    })).toBe(false);
    expect(shouldHandleDockRequest({
      role: 'host',
      sourceWindowId: 'float-1',
      thisWindowId: 'host-1',
    })).toBe(true);
    expect(shouldHandleDockRequest({
      role: 'host',
      sourceWindowId: 'float-1',
      thisWindowId: 'host-1',
      targetWindowId: 'other-host',
    })).toBe(false);
    expect(shouldHandleDockRequest({
      role: 'float',
      sourceWindowId: 'float-1',
      thisWindowId: 'float-1',
    })).toBe(false);
  });

  it('lets only one host claim a dock-request', () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
    };
    expect(claimDockTarget(storage, 'req-1', 'host-a')).toBe(true);
    expect(claimDockTarget(storage, 'req-1', 'host-b')).toBe(false);
    expect(claimDockTarget(storage, 'req-1', 'host-a')).toBe(true);
    expect(claimDockTarget(storage, 'req-2', 'host-b')).toBe(true);
  });
});
