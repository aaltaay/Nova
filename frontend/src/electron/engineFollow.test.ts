import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  AUTO_RESTART_NO_ANSWER,
  ENGINE_FOLLOW_FILE,
  ENGINE_FOLLOW_MAX_AGE_MS,
  autoRestartHolds,
  restartCheckLines,
  takeEngineFollow,
  writeEngineFollow,
} from '../../electron/engineFollow.mjs';

let dir = '';

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-follow-'));
});

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

describe("the old desk's promise to the new one (one version)", () => {
  it('is read once, then gone', () => {
    expect(writeEngineFollow(dir, { tag: 'v1051', repoRoot: 'C:\\Nova', now: 1_000 })).toBe(true);
    expect(takeEngineFollow(dir, { now: 2_000 })).toEqual({ tag: 'v1051', repo_root: 'C:\\Nova', asked_at: 1_000 });
    expect(fs.existsSync(path.join(dir, ENGINE_FOLLOW_FILE))).toBe(false);
    expect(takeEngineFollow(dir, { now: 2_000 })).toBeNull();
  });

  it('reads an old, unknown or unreadable promise as none, and deletes it', () => {
    writeEngineFollow(dir, { tag: 'v1051', repoRoot: null, now: 0 });
    expect(takeEngineFollow(dir, { now: ENGINE_FOLLOW_MAX_AGE_MS + 1 })).toBeNull();
    fs.writeFileSync(path.join(dir, ENGINE_FOLLOW_FILE), JSON.stringify({ schema_version: 2, tag: 'v1051', asked_at: 1 }));
    expect(takeEngineFollow(dir, { now: 2 })).toBeNull();
    fs.writeFileSync(path.join(dir, ENGINE_FOLLOW_FILE), '{not json');
    expect(takeEngineFollow(dir, { now: 2 })).toBeNull();
    expect(fs.existsSync(path.join(dir, ENGINE_FOLLOW_FILE))).toBe(false);
  });

  it('never writes a promise for something that is not a release', () => {
    expect(writeEngineFollow(dir, { tag: 'dev', repoRoot: null })).toBe(false);
    expect(fs.existsSync(path.join(dir, ENGINE_FOLLOW_FILE))).toBe(false);
  });
});

describe('restartCheckLines', () => {
  it('is safe only when the backend answered with nothing open', () => {
    expect(restartCheckLines({ schema_version: 1, safe: true, open: [], unknown: [] })).toEqual({ safe: true, lines: [] });
    const open = restartCheckLines({
      schema_version: 1,
      safe: false,
      open: [{ kind: 'position', text: 'Paper: 100 MSGY' }],
      unknown: [{ kind: 'ibkr', error: 'timeout' }],
    });
    expect(open).toEqual({ safe: false, lines: ['Paper: 100 MSGY', 'Could not read ibkr: timeout'] });
    expect(restartCheckLines(null).safe).toBeNull();
  });
});

describe('autoRestartHolds (what keeps the desk from restarting by itself)', () => {
  const check = (open: unknown[], extra: Record<string, unknown> = {}) => ({
    schema_version: 1,
    safe: open.length ? false : true,
    open,
    unknown: [],
    ...extra,
  });

  it('a recording does not hold it: it resumes by itself after a few seconds', () => {
    expect(autoRestartHolds(check([]))).toEqual([]);
    expect(autoRestartHolds(check([{ kind: 'recording', text: 'Recording MNDR: a few seconds gap' }]))).toEqual([]);
  });

  it("everything else holds it, in the backend's words -- a kind this desk does not know too", () => {
    const open = [
      { kind: 'recording', text: 'Recording MNDR' },
      { kind: 'position', text: 'Paper position MNDR 100' },
      { kind: 'working_order', text: 'IBKR working order SELL 100 MNDR LMT 3.1' },
      { kind: 'bell', text: 'The opening bell (09:25-09:45 ET)' },
      { kind: 'bot_trade', text: 'Bot trade MNDR (holding)' },
      { kind: 'stock_mode', text: 'MNDR is set to Buy Nova' },
      { kind: 'download', text: '1 history download running' },
      { kind: 'something_new' },
    ];
    expect(autoRestartHolds(check(open))).toEqual([
      'Paper position MNDR 100',
      'IBKR working order SELL 100 MNDR LMT 3.1',
      'The opening bell (09:25-09:45 ET)',
      'Bot trade MNDR (holding)',
      'MNDR is set to Buy Nova',
      '1 history download running',
      'Something open (something_new)',
    ]);
  });

  it('a backend that cannot say holds it: never read as nothing open', () => {
    expect(autoRestartHolds(null)).toEqual([AUTO_RESTART_NO_ANSWER]);
    expect(autoRestartHolds({ schema_version: 2, safe: true, open: [], unknown: [] })).toEqual([AUTO_RESTART_NO_ANSWER]);
    expect(autoRestartHolds({ schema_version: 1, safe: true, unknown: [] })).toEqual([AUTO_RESTART_NO_ANSWER]);
    expect(autoRestartHolds(check([], { safe: null, unknown: [{ kind: 'ibkr', error: 'timeout' }] }))).toEqual([
      'Could not read ibkr: timeout',
    ]);
    expect(autoRestartHolds(check([], { safe: null }))).toEqual([AUTO_RESTART_NO_ANSWER]);
  });
});
