import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  ENGINE_FOLLOW_FILE,
  ENGINE_FOLLOW_MAX_AGE_MS,
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
