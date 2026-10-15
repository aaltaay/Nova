/**
 * The automatic download and install (operator ask 2026-10-14: "I want an auto update"): a newer
 * release goes by itself only when nothing is at stake -- outside weekday trading hours, nothing open
 * on the backend but a recording, and, for the install, no keyboard or mouse input for 5 minutes.
 */
import { describe, expect, it, vi } from 'vitest';
import { createAutoInstall } from '../../electron/autoInstall.mjs';
import { AUTO_RESTART_NO_ANSWER } from '../../electron/engineFollow.mjs';
import {
  AUTO_WAIT_IDLE,
  AUTO_WAIT_TRADING_HOURS,
  INITIAL_UPDATE_STATE,
  UPDATE_AUTO_IDLE_MS,
  reduceUpdateState,
} from '../../electron/updatePolicy.mjs';

type State = typeof INITIAL_UPDATE_STATE & { auto: { waiting: string[] } | null };
type Event = { type: string; version?: string; auto?: unknown };

const EVENING = Date.parse('2026-09-23T21:00:00Z'); // Wednesday 17:00 ET
const TRADING_HOURS = Date.parse('2026-09-23T14:00:00Z'); // Wednesday 10:00 ET
const SATURDAY_MORNING = Date.parse('2026-09-26T14:00:00Z'); // Saturday 10:00 ET
const VERSION = '0.1.832';

const found = (): State => [{ type: 'checking' }, { type: 'available', version: VERSION }].reduce(reduceUpdateState, INITIAL_UPDATE_STATE);
const ready = (): State => [{ type: 'offered', version: VERSION }, { type: 'download' }, { type: 'downloaded', version: VERSION }]
  .reduce(reduceUpdateState, found());

function harness({
  state = found(),
  holds = [[]] as (string[] | null | Error)[],
  idleMs = UPDATE_AUTO_IDLE_MS,
  now = EVENING,
  enabled = true,
  installs = [true],
}: {
  state?: State;
  holds?: (string[] | null | Error)[];
  idleMs?: number | (() => number);
  now?: number;
  enabled?: boolean;
  installs?: boolean[];
} = {}) {
  let current = state;
  const dispatch = vi.fn((event: Event) => {
    current = reduceUpdateState(current, event);
  });
  const holdsFn = vi.fn(async () => {
    const next = holds.length > 1 ? holds.shift() : holds[0];
    if (next instanceof Error) throw next;
    return next ?? null;
  });
  const download = vi.fn(async () => dispatch({ type: 'download' }));
  const install = vi.fn(async () => (installs.length > 1 ? installs.shift() : installs[0]) ?? false);
  const logger = { info: vi.fn(), warn: vi.fn() };
  const auto = createAutoInstall({
    getState: () => current,
    dispatch,
    enabled: () => enabled,
    holds: holdsFn,
    idleMs: typeof idleMs === 'function' ? idleMs : () => idleMs,
    download,
    install,
    logger,
    now: () => now,
  });
  return { auto, state: () => current, holds: holdsFn, download, install, logger, dispatch };
}

describe('the automatic download', () => {
  it('downloads a found release by itself once nothing is open, outside trading hours', async () => {
    const h = harness();
    expect(await h.auto.step()).toBe(true);
    expect(h.download).toHaveBeenCalledTimes(1);
    expect(h.state().phase).toBe('downloading');
    expect(h.logger.info).toHaveBeenCalledWith(expect.stringContaining('downloading v832 by itself'));
  });

  it('downloads on a weekend morning: the trading-hours hold is weekdays only', async () => {
    const h = harness({ now: SATURDAY_MORNING });
    expect(await h.auto.step()).toBe(true);
  });

  it('waits out weekday trading hours without asking the backend', async () => {
    const h = harness({ now: TRADING_HOURS });
    expect(await h.auto.step()).toBe(false);
    expect(h.download).not.toHaveBeenCalled();
    expect(h.holds).not.toHaveBeenCalled();
    expect(h.state().auto).toEqual({ waiting: [AUTO_WAIT_TRADING_HOURS] });
  });

  it('waits while anything but a recording is open, and says what', async () => {
    const h = harness({ holds: [['Paper: long 100 GENK']] });
    expect(await h.auto.step()).toBe(false);
    expect(h.download).not.toHaveBeenCalled();
    expect(h.state().auto).toEqual({ waiting: ['Paper: long 100 GENK'] });
    expect(h.logger.info).toHaveBeenCalledWith(expect.stringContaining('waiting for: Paper: long 100 GENK'));
  });

  it('reads a backend that did not answer, or a read that failed, as something open', async () => {
    const silent = harness({ holds: [null] });
    expect(await silent.auto.step()).toBe(false);
    expect(silent.state().auto).toEqual({ waiting: [AUTO_RESTART_NO_ANSWER] });
    const failed = harness({ holds: [new Error('connect ECONNREFUSED 127.0.0.1:8000')] });
    expect(await failed.auto.step()).toBe(false);
    expect(failed.state().auto?.waiting[0]).toContain('Could not read what is open');
  });

  it('logs what it waits for once, not on every look', async () => {
    const h = harness({ holds: [['Paper: long 100 GENK']] });
    await h.auto.step();
    await h.auto.step();
    const waits = h.logger.info.mock.calls.filter(([line]) => String(line).includes('waiting for'));
    expect(waits).toHaveLength(1);
  });
});

describe('the automatic install', () => {
  it('installs once nothing is open and nobody touched the desk for 5 minutes', async () => {
    const h = harness({ state: ready() });
    expect(await h.auto.step()).toBe(true);
    expect(h.install).toHaveBeenCalledTimes(1);
  });

  it('waits while the operator is at the keyboard or mouse', async () => {
    const h = harness({ state: ready(), idleMs: UPDATE_AUTO_IDLE_MS - 1 });
    expect(await h.auto.step()).toBe(false);
    expect(h.install).not.toHaveBeenCalled();
    expect(h.state().auto).toEqual({ waiting: [AUTO_WAIT_IDLE] });
  });

  it('reads an idle time it cannot get as the desk in use', async () => {
    const h = harness({
      state: ready(),
      idleMs: () => {
        throw new Error('powerMonitor unavailable');
      },
    });
    expect(await h.auto.step()).toBe(false);
    expect(h.install).not.toHaveBeenCalled();
    expect(h.logger.warn).toHaveBeenCalled();
  });

  it('lists what is open and the idle wait together', async () => {
    const h = harness({ state: ready(), holds: [['Live: working order']], idleMs: 0 });
    await h.auto.step();
    expect(h.state().auto).toEqual({ waiting: ['Live: working order', AUTO_WAIT_IDLE] });
  });

  it('a trade placed while the backend was prepared waits for the next look', async () => {
    const h = harness({ state: ready(), holds: [[], ['Paper: long 100 GENK'], []], installs: [false, true] });
    expect(await h.auto.step()).toBe(false);
    expect(h.state().auto).toEqual({ waiting: ['Paper: long 100 GENK'] });
    expect(await h.auto.step()).toBe(true);
    expect(h.install).toHaveBeenCalledTimes(2);
  });

  it("an install that cannot go ahead for anything else is left to the operator's click", async () => {
    const h = harness({ state: ready(), installs: [false] });
    expect(await h.auto.step()).toBe(false);
    expect(h.state().auto).toBeNull();
    expect(h.logger.warn).toHaveBeenCalledWith(expect.stringContaining('left to Restart to update'));
    await h.auto.step();
    expect(h.install).toHaveBeenCalledTimes(1);
  });
});

describe("when it is the operator's", () => {
  it('does nothing with the automatic install off', async () => {
    const h = harness({ enabled: false });
    expect(await h.auto.step()).toBe(false);
    expect(h.holds).not.toHaveBeenCalled();
    expect(h.state().auto).toBeNull();
  });

  it('leaves a version the operator answered Later for alone', async () => {
    const later = [{ type: 'offered', version: VERSION }, { type: 'dismissed', version: VERSION }].reduce(reduceUpdateState, found());
    const h = harness({ state: later });
    expect(await h.auto.step()).toBe(false);
    expect(h.download).not.toHaveBeenCalled();
  });

  it('acts on nothing that moved while the backend answered', async () => {
    let release: (lines: string[]) => void = () => {};
    const h = harness();
    h.holds.mockImplementationOnce(() => new Promise<string[]>((resolve) => { release = resolve; }));
    const look = h.auto.step();
    h.dispatch({ type: 'download' }); // the operator pressed Update meanwhile
    release([]);
    expect(await look).toBe(false);
    expect(h.download).not.toHaveBeenCalled();
  });

  it('one look at a time', async () => {
    let release: (lines: string[]) => void = () => {};
    const h = harness();
    h.holds.mockImplementationOnce(() => new Promise<string[]>((resolve) => { release = resolve; }));
    const first = h.auto.step();
    expect(await h.auto.step()).toBe(false);
    release([]);
    expect(await first).toBe(true);
    expect(h.download).toHaveBeenCalledTimes(1);
  });
});
