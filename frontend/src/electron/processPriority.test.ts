import { describe, expect, it } from 'vitest';
// @ts-expect-error -- plain ESM module from the Electron main process
import { deskPids, raisePids } from '../../electron/processPriority.mjs';

// ADR 045: on 2026-10-05 explorer.exe and everything it started ran BelowNormal beside a game booster.
const PRIORITY = { PRIORITY_LOW: 19, PRIORITY_BELOW_NORMAL: 10, PRIORITY_NORMAL: 0, PRIORITY_ABOVE_NORMAL: -7, PRIORITY_HIGH: -14 };

function fakeOs(start: Record<number, number>) {
  const nice = new Map(Object.entries(start).map(([pid, v]) => [Number(pid), v]));
  return {
    constants: { priority: PRIORITY },
    getPriority: (pid: number) => {
      if (!nice.has(pid)) throw new Error('no such process');
      return nice.get(pid);
    },
    setPriority: (pid: number, value: number) => nice.set(pid, value),
    nice,
  };
}

function win(pid: number, desk = true) {
  return { desk, isDestroyed: () => false, webContents: { getOSProcessId: () => pid } };
}

describe('the desk keeps its processes above background work', () => {
  it('keeps the main process, the GPU process and desk windows, never the recorder pages', () => {
    const pids = deskPids({
      mainPid: 1,
      metrics: [{ type: 'Browser', pid: 1 }, { type: 'GPU', pid: 2 }, { type: 'Tab', pid: 3 }, { type: 'Tab', pid: 4 }],
      windows: [win(3), win(4, false)],
      isDeskWindow: (w: { desk: boolean }) => w.desk,
    });
    expect([...pids].sort()).toEqual([1, 2, 3]);
  });

  it('raises what reads lower and never lowers anything', () => {
    const os = fakeOs({ 1: PRIORITY.PRIORITY_BELOW_NORMAL, 2: PRIORITY.PRIORITY_NORMAL, 3: PRIORITY.PRIORITY_HIGH });
    const { raised, failed } = raisePids(os, new Set([1, 2, 3, 99]));
    expect(raised.sort()).toEqual([1, 2]);
    expect(os.nice.get(1)).toBe(PRIORITY.PRIORITY_ABOVE_NORMAL);
    expect(os.nice.get(3)).toBe(PRIORITY.PRIORITY_HIGH);
    expect(failed.map((f: { pid: number }) => f.pid)).toEqual([99]);
  });
});
