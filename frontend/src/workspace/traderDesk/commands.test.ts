import { describe, expect, it } from 'vitest';
import {
  claimDockTarget,
  closePolicyAfterGive,
  deskRoleFromStockView,
  isForeignTabDrag,
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

  it('ignores a drag that originated in this window', () => {
    expect(isForeignTabDrag('win-a', 'win-b')).toBe(true);
    expect(isForeignTabDrag('win-a', 'win-a')).toBe(false);
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
