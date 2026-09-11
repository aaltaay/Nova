/**
 * @vitest-environment jsdom
 *
 * `event.repeat` only filters a held key. A second press while the first
 * order is still in flight is a real second gesture (D-011).
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';

const runNovaActionMock = vi.fn();

vi.mock('./runNovaAction', () => ({
  runNovaAction: (...args: unknown[]) => runNovaActionMock(...args),
}));
vi.mock('../ibkr/notifyOrderRejected', () => ({
  notifyOrderRejected: vi.fn(),
}));

import {
  HotkeyDispatchProvider,
  useHotkeyDispatch,
} from './HotkeyDispatchContext';

const ACTION: NovaActionRecord = {
  id: 'exit-1',
  name: 'Exit position',
  kind: 'exit_pos',
  key: { label: 'Ctrl+1', key: '1', ctrl: true },
  params: {},
  enabled: true,
  showButton: true,
};

describe('HotkeyDispatchProvider in-flight guard', () => {
  beforeEach(() => {
    runNovaActionMock.mockReset();
  });

  it('refuses a second run of the same action until the first settles', async () => {
    let settle: (value: NovaActionResult) => void = () => undefined;
    runNovaActionMock.mockImplementation(
      () => new Promise<NovaActionResult>((resolve) => { settle = resolve; }),
    );
    const { result } = renderHook(() => useHotkeyDispatch(), {
      wrapper: HotkeyDispatchProvider,
    });

    let first: Promise<NovaActionResult> | null = null;
    let blocked: NovaActionResult | null = null;
    await act(async () => {
      first = result.current.runAction(ACTION);
      blocked = await result.current.runAction(ACTION);
    });
    expect(runNovaActionMock).toHaveBeenCalledTimes(1);
    expect(blocked!.ok).toBe(false);
    expect(blocked!.text).toMatch(/still running/i);

    await act(async () => {
      settle({ ok: true, text: 'Exit order #7' });
      await first;
    });

    runNovaActionMock.mockResolvedValue({ ok: true, text: 'Exit order #8' });
    await act(async () => {
      await result.current.runAction(ACTION);
    });
    expect(runNovaActionMock).toHaveBeenCalledTimes(2);
  });
});
