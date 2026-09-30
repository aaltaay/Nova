import { describe, expect, it, vi } from 'vitest';

vi.mock('../../electron/updateSplash.mjs', () => ({ showUpdateSplash: () => ({ close: vi.fn() }) }));

import { createReleaseInstaller } from '../../electron/releaseInstall.mjs';

function installer(prepare: (tag: string) => Promise<boolean>) {
  const quitAndInstall = vi.fn();
  const dispatch = vi.fn();
  const stopEngine = vi.fn(async () => true);
  const inst = createReleaseInstaller({
    getUpdater: () => ({ quitAndInstall }),
    getState: () => ({ phase: 'ready', version: '0.1.1051' }),
    dispatch,
    prepare,
    stopEngine,
    restartEngine: vi.fn(async () => undefined),
    box: vi.fn(),
    logsDir: () => '',
    logger: { info: vi.fn(), error: vi.fn() },
  });
  return { inst, quitAndInstall, dispatch, stopEngine };
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
    const { inst, quitAndInstall, dispatch, stopEngine } = installer(async () => false);
    await inst.install();
    expect(quitAndInstall).not.toHaveBeenCalled();
    expect(stopEngine).not.toHaveBeenCalled();
    expect(dispatch).not.toHaveBeenCalled();
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
