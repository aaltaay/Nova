import { describe, expect, it, vi } from 'vitest';

vi.mock('../../electron/updateSplash.mjs', () => ({ showUpdateSplash: () => ({ close: vi.fn() }) }));

import { createReleaseInstaller } from '../../electron/releaseInstall.mjs';

function installer(
  prepare: (tag: string) => Promise<boolean>,
  { order = [] as string[], stopped = true, handOff = async () => { order.push('handOff'); } } = {},
) {
  const quitAndInstall = vi.fn(() => { order.push('install'); });
  const dispatch = vi.fn();
  const stopEngine = vi.fn(async () => {
    order.push('stopEngine');
    return stopped;
  });
  const handOffFn = vi.fn(handOff);
  const inst = createReleaseInstaller({
    getUpdater: () => ({ quitAndInstall }),
    getState: () => ({ phase: 'ready', version: '0.1.1051' }),
    dispatch,
    prepare,
    stopEngine,
    handOff: handOffFn,
    restartEngine: vi.fn(async () => undefined),
    box: vi.fn(),
    logsDir: () => '',
    logger: { info: vi.fn(), error: vi.fn() },
  });
  return { inst, quitAndInstall, dispatch, stopEngine, handOff: handOffFn };
}

describe('Restart to update carries the backend first (one version)', () => {
  it('prepares the backend for the release, then installs', async () => {
    const prepare = vi.fn(async () => true);
    const { inst, quitAndInstall } = installer(prepare);
    await inst.install();
    expect(prepare).toHaveBeenCalledWith('v1051');
    expect(quitAndInstall).toHaveBeenCalledWith(true, true);
  });

  it('installs nothing, and stops nothing, when the operator chose to wait', async () => {
    const { inst, quitAndInstall, dispatch, stopEngine, handOff } = installer(async () => false);
    await inst.install();
    expect(quitAndInstall).not.toHaveBeenCalled();
    expect(stopEngine).not.toHaveBeenCalled();
    expect(handOff).not.toHaveBeenCalled();
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('restarts the backend before the installer runs, so it comes up during the install', async () => {
    const order: string[] = [];
    const { inst } = installer(async () => true, { order });
    await inst.install();
    expect(order).toEqual(['stopEngine', 'handOff', 'install']);
  });

  it('a backend restart that fails still installs: the new desk restarts it instead', async () => {
    const order: string[] = [];
    const { inst, quitAndInstall } = installer(async () => true, {
      order,
      handOff: async () => {
        throw new Error('Not restarted: backend v1050 is still running');
      },
    });
    await inst.install();
    expect(quitAndInstall).toHaveBeenCalledWith(true, true);
  });

  it('restarts no backend when the install cannot go ahead', async () => {
    const { inst, quitAndInstall, handOff } = installer(async () => true, { stopped: false });
    await inst.install();
    expect(handOff).not.toHaveBeenCalled();
    expect(quitAndInstall).not.toHaveBeenCalled();
  });

  it('a second press while the backend is being prepared does nothing', async () => {
    let release: (value: boolean) => void = () => {};
    const prepare = vi.fn(() => new Promise<boolean>((resolve) => { release = resolve; }));
    const { inst, quitAndInstall } = installer(prepare);
    const first = inst.install();
    await inst.install();
    release(true);
    await first;
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(quitAndInstall).toHaveBeenCalledTimes(1);
  });
});
