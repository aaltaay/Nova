/**
 * @vitest-environment jsdom
 *
 * QA R35: the dispatcher publishes each Nova Action outcome stamped with a
 * run number and the symbol it ran on, so the ticket for that symbol can
 * show it on its Last line -- a repeat of the same text included.
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

import { HotkeyDispatchProvider, useHotkeyDispatch } from './HotkeyDispatchContext';

const ACTION: NovaActionRecord = {
  id: 'exit-1',
  name: 'Exit position',
  kind: 'exit_pos',
  key: { label: 'Ctrl+1', key: '1', ctrl: true },
  params: {},
  enabled: true,
  showButton: true,
};

describe('HotkeyDispatchProvider outcomes', () => {
  beforeEach(() => {
    runNovaActionMock.mockReset();
  });

  it('stamps each outcome with a new run number and the symbol it ran on', async () => {
    runNovaActionMock.mockResolvedValue({ ok: true, text: 'Exit order #12' });
    const { result } = renderHook(() => useHotkeyDispatch(), { wrapper: HotkeyDispatchProvider });
    act(() => result.current.setRuntime({ symbol: 'GRML' }));

    await act(async () => { await result.current.runAction(ACTION); });
    expect(result.current.lastResult).toMatchObject({ ok: true, text: 'Exit order #12', symbol: 'GRML' });
    const first = result.current.lastResult!.seq;

    // The same text again is a new outcome, not the old one.
    await act(async () => { await result.current.runAction(ACTION); });
    expect(result.current.lastResult).toMatchObject({ text: 'Exit order #12', symbol: 'GRML' });
    expect(result.current.lastResult!.seq).toBeGreaterThan(first);
  });

  it('names the symbol the action started on, even if the desk moved on while it ran', async () => {
    let settle: (value: NovaActionResult) => void = () => undefined;
    runNovaActionMock.mockImplementation(
      () => new Promise<NovaActionResult>((resolve) => { settle = resolve; }),
    );
    const { result } = renderHook(() => useHotkeyDispatch(), { wrapper: HotkeyDispatchProvider });
    act(() => result.current.setRuntime({ symbol: 'GRML' }));
    let run: Promise<NovaActionResult> | null = null;
    act(() => { run = result.current.runAction(ACTION); });
    act(() => result.current.setRuntime({ symbol: 'AAPL' }));
    await act(async () => {
      settle({ ok: false, text: 'Exit refused' });
      await run;
    });
    expect(result.current.lastResult).toMatchObject({ ok: false, text: 'Exit refused', symbol: 'GRML' });
  });
});
