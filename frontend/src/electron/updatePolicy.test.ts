import { describe, expect, it } from 'vitest';
import {
  INITIAL_UPDATE_STATE,
  LATER_BUTTON,
  RESTART_BUTTON,
  UPDATE_RECHECK_INTERVAL_MS,
  displayTag,
  easternClock,
  errorText,
  inUpdateQuietHours,
  isRestartChoice,
  manualCheckAction,
  manualCheckResult,
  reduceUpdateState,
  resolveUpdateSetting,
  restartPrompt,
  shouldAutoCheck,
  shouldPromptNow,
  shouldPromptRestart,
  shouldRecheck,
  taskbarProgress,
  updateCheckSetting,
  updateGate,
  updateMenuItems,
} from '../../electron/updatePolicy.mjs';

type UpdateEvent = { type: string; version?: string; percent?: number; message?: unknown };
const run = (...events: UpdateEvent[]) => events.reduce(reduceUpdateState, INITIAL_UPDATE_STATE);
const AUTO = { updater: true, automatic: true, reason: '' };
const readyAt = (version: string) =>
  run({ type: 'checking' }, { type: 'available', version }, { type: 'downloaded', version });

describe('update gate', () => {
  it('never updates a dev checkout or a non-Windows build', () => {
    expect(updateGate({ isPackaged: false, platform: 'win32', setting: '' }).updater).toBe(false);
    expect(updateGate({ isPackaged: true, platform: 'darwin', setting: '' }).updater).toBe(false);
  });

  it('checks automatically on a packaged Windows desk unless switched off', () => {
    expect(updateGate({ isPackaged: true, platform: 'win32', setting: '' })).toEqual(AUTO);
    for (const off of ['0', 'false', 'NO', ' off ']) {
      const gate = updateGate({ isPackaged: true, platform: 'win32', setting: off });
      expect(gate.updater).toBe(true); // Help > Check for Updates still works offline-by-choice
      expect(gate.automatic).toBe(false);
    }
    expect(updateCheckSetting('1')).toBe(true);
    expect(updateCheckSetting(undefined)).toBe(true);
  });

  it('lets the process env override the desk .env', () => {
    expect(resolveUpdateSetting({ processValue: '0', fileValue: '1' })).toBe('0');
    expect(resolveUpdateSetting({ processValue: '  ', fileValue: 'off' })).toBe('off');
    expect(resolveUpdateSetting({})).toBe('');
  });
});

describe('update state', () => {
  it('walks check -> download -> ready and shows progress on the taskbar', () => {
    const downloading = run({ type: 'checking' }, { type: 'available', version: '0.1.832' }, { type: 'progress', percent: 41.6 });
    expect(downloading.phase).toBe('downloading');
    expect(taskbarProgress(downloading)).toBeCloseTo(0.416);
    const ready = reduceUpdateState(downloading, { type: 'downloaded', version: '0.1.832' });
    expect(ready.phase).toBe('ready');
    expect(taskbarProgress(ready)).toBe(-1);
  });

  it('keeps a downloaded installer when a later check fails or runs', () => {
    const ready = readyAt('0.1.832');
    expect(reduceUpdateState(ready, { type: 'checking' }).phase).toBe('ready');
    expect(reduceUpdateState(ready, { type: 'not-available' }).phase).toBe('ready');
    const failed = reduceUpdateState(ready, { type: 'error', message: 'offline' });
    expect(failed.phase).toBe('ready');
    expect(failed.error).toBe('offline');
  });

  it('turns an offline check into a visible, retryable failure', () => {
    const failed = run({ type: 'checking' }, { type: 'error', message: new Error('net::ERR_INTERNET_DISCONNECTED\n  at stack') });
    expect(failed.phase).toBe('failed');
    expect(failed.error).toBe('net::ERR_INTERNET_DISCONNECTED');
    expect(manualCheckAction(failed, AUTO)).toBe('check');
    expect(updateMenuItems(failed)[0]).toEqual({ label: 'Update check failed — Retry', action: 'check' });
    expect(manualCheckResult(failed)?.type).toBe('warning');
  });

  it('names a stopped download as a download, keeps its percent, and offers Resume', () => {
    const failed = run(
      { type: 'checking' },
      { type: 'available', version: '0.1.961' },
      { type: 'progress', percent: 45.7 },
      { type: 'error', message: 'net::ERR_SSL_PROTOCOL_ERROR' },
    );
    expect(failed).toMatchObject({ phase: 'failed', failedStage: 'download', percent: 45.7 });
    expect(updateMenuItems(failed).slice(0, 2)).toEqual([
      { label: 'Download of v961 stopped at 45% — Resume', action: 'check' },
      { label: 'net::ERR_SSL_PROTOCOL_ERROR' },
    ]);
    expect(manualCheckAction(failed, AUTO)).toBe('check');
    expect(manualCheckResult(failed)?.message).toBe('Nova could not finish downloading v961.');
    expect(manualCheckResult(failed)?.detail).toContain('What already arrived is kept');
    // The next attempt is a fresh check, not a download failure.
    const again = reduceUpdateState(failed, { type: 'checking' });
    expect(again).toMatchObject({ phase: 'checking', failedStage: '' });
  });

  it('shows a chunk retry while downloading and clears it once bytes arrive', () => {
    const downloading = run({ type: 'checking' }, { type: 'available', version: '0.1.961' }, { type: 'progress', percent: 10 });
    const retrying = reduceUpdateState(downloading, { type: 'retrying', attempt: 2 } as UpdateEvent);
    expect(updateMenuItems(retrying)[1]).toEqual({ label: 'Connection dropped; retrying (attempt 2)' });
    const moving = reduceUpdateState(retrying, { type: 'progress', percent: 20 });
    expect(moving.retry).toBe(0);
    // A retry outside a download means nothing.
    expect(reduceUpdateState(INITIAL_UPDATE_STATE, { type: 'retrying', attempt: 1 } as UpdateEvent)).toBe(INITIAL_UPDATE_STATE);
  });

  it('returns to ready when an install attempt fails, so the operator can retry', () => {
    const installing = reduceUpdateState(readyAt('0.1.832'), { type: 'installing' });
    expect(installing.phase).toBe('installing');
    const back = reduceUpdateState(installing, { type: 'install-failed', message: 'engine did not stop' });
    expect(back.phase).toBe('ready');
    expect(updateMenuItems(back)[0]).toEqual({ label: 'Restart to Update (v832)', action: 'restart' });
  });

  it('only installs from ready', () => {
    expect(reduceUpdateState(INITIAL_UPDATE_STATE, { type: 'installing' }).phase).toBe('idle');
  });
});

describe('prompt policy', () => {
  it('prompts once per version; Later is not re-asked this session', () => {
    const ready = readyAt('0.1.832');
    expect(shouldPromptRestart(ready)).toBe(true);
    const prompted = reduceUpdateState(ready, { type: 'prompted', version: '0.1.832' });
    expect(shouldPromptRestart(prompted)).toBe(false);
    // An explicit Help-menu request re-offers it.
    expect(manualCheckAction(prompted, AUTO)).toBe('prompt');
  });

  it('defaults to Later so a stray Enter never restarts the desk', () => {
    const prompt = restartPrompt('0.1.832');
    expect(prompt.buttons[RESTART_BUTTON]).toBe('Restart to update');
    expect(prompt.buttons[LATER_BUTTON]).toBe('Later');
    expect(prompt.defaultId).toBe(LATER_BUTTON);
    expect(prompt.cancelId).toBe(LATER_BUTTON);
    expect(prompt.message).toContain('v832');
    expect(isRestartChoice(RESTART_BUTTON)).toBe(true);
    expect(isRestartChoice(LATER_BUTTON)).toBe(false);
    expect(isRestartChoice(-1)).toBe(false);
  });

  it('checks automatically only when idle, and never while busy or ready', () => {
    expect(shouldAutoCheck(INITIAL_UPDATE_STATE, AUTO)).toBe(true);
    expect(shouldAutoCheck(INITIAL_UPDATE_STATE, { ...AUTO, automatic: false })).toBe(false);
    expect(shouldAutoCheck(run({ type: 'checking' }), AUTO)).toBe(false);
    expect(shouldAutoCheck(readyAt('0.1.832'), AUTO)).toBe(false);
    expect(manualCheckAction(run({ type: 'checking' }), AUTO)).toBe('busy');
    expect(manualCheckAction(INITIAL_UPDATE_STATE, { updater: false, automatic: false })).toBe('unavailable');
  });
});

describe('re-checks while the desk stays open', () => {
  const at = (iso: string) => Date.parse(iso);

  it('holds weekday 07:00-16:00 on the Eastern clock, daylight time or not', () => {
    expect(easternClock(at('2026-09-23T11:00:00Z'))).toEqual({ weekday: 'Wed', minute: 7 * 60 });
    expect(inUpdateQuietHours(at('2026-09-23T10:59:00Z'))).toBe(false); // Wed 06:59 EDT
    expect(inUpdateQuietHours(at('2026-09-23T11:00:00Z'))).toBe(true); // 07:00 EDT
    expect(inUpdateQuietHours(at('2026-09-23T19:59:00Z'))).toBe(true); // 15:59 EDT
    expect(inUpdateQuietHours(at('2026-09-23T20:00:00Z'))).toBe(false); // 16:00 EDT
    expect(inUpdateQuietHours(at('2026-12-02T11:30:00Z'))).toBe(false); // Wed 06:30 EST
    expect(inUpdateQuietHours(at('2026-12-02T12:30:00Z'))).toBe(true); // 07:30 EST
    expect(inUpdateQuietHours(at('2026-09-26T14:00:00Z'))).toBe(false); // Saturday 10:00
  });

  it('re-checks once per interval outside trading hours, and never while busy or ready', () => {
    const evening = at('2026-09-23T22:00:00Z'); // Wed 18:00 EDT
    const since = (ms: number) => ({ now: evening, lastCheckAt: evening - ms });
    const current = run({ type: 'checking' }, { type: 'not-available' });
    expect(shouldRecheck(current, AUTO, since(UPDATE_RECHECK_INTERVAL_MS))).toBe(true);
    expect(shouldRecheck(current, AUTO, since(UPDATE_RECHECK_INTERVAL_MS - 1))).toBe(false);
    expect(shouldRecheck(current, { ...AUTO, automatic: false }, since(UPDATE_RECHECK_INTERVAL_MS))).toBe(false);
    expect(shouldRecheck(run({ type: 'checking' }), AUTO, since(UPDATE_RECHECK_INTERVAL_MS))).toBe(false);
    expect(shouldRecheck(readyAt('0.1.832'), AUTO, since(UPDATE_RECHECK_INTERVAL_MS))).toBe(false);
    // A failed check, or a download that stopped, is tried again.
    const failed = run({ type: 'checking' }, { type: 'error', message: 'offline' });
    expect(shouldRecheck(failed, AUTO, since(UPDATE_RECHECK_INTERVAL_MS))).toBe(true);
    const tradingHours = at('2026-09-23T14:00:00Z'); // Wed 10:00 EDT
    expect(shouldRecheck(current, AUTO, { now: tradingHours, lastCheckAt: 0 })).toBe(false);
  });

  it("asks at once after a launch or Help-menu check, and holds a re-check's prompt until 16:00", () => {
    const ready = readyAt('0.1.832');
    const tradingHours = at('2026-09-23T14:00:00Z'); // Wed 10:00 EDT
    const afterClose = at('2026-09-23T20:10:00Z'); // 16:10 EDT
    expect(shouldPromptNow(ready, { origin: 'launch', now: tradingHours })).toBe(true);
    expect(shouldPromptNow(ready, { origin: 'manual', now: tradingHours })).toBe(true);
    expect(shouldPromptNow(ready, { origin: 'recheck', now: tradingHours })).toBe(false);
    expect(shouldPromptNow(ready, { origin: 'recheck', now: afterClose })).toBe(true);
    const prompted = reduceUpdateState(ready, { type: 'prompted', version: '0.1.832' });
    expect(shouldPromptNow(prompted, { origin: 'recheck', now: afterClose })).toBe(false);
  });
});

describe('labels', () => {
  it('maps packaged semver to the public vNNN tag', () => {
    expect(displayTag('0.1.832')).toBe('v832');
    expect(displayTag('v045')).toBe('v045');
    expect(displayTag('')).toBe('');
  });

  it('keeps error text to one short line', () => {
    expect(errorText('x'.repeat(400)).length).toBeLessThanOrEqual(160);
    expect(errorText(undefined)).toBe('unknown error');
  });

  it('always shows the installed version and an automatic-off note', () => {
    const rows = updateMenuItems(run({ type: 'checking' }, { type: 'not-available' }), {
      currentTag: 'v831',
      automatic: false,
    });
    expect(rows.map((row) => row.label)).toEqual([
      'Check for Updates…',
      'This is the latest release',
      'Installed: Nova v831',
      'Automatic checks off (NOVA_UPDATE_CHECK)',
    ]);
    expect(manualCheckResult(run({ type: 'not-available' }), 'v831')?.message).toBe(
      'Nova v831 is the latest release.',
    );
  });
});
