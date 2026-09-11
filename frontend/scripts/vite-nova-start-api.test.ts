import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { acquireLock, isLockStale, LOCK_PATH, releaseLock } from './vite-nova-start-api';

const TEST_LOCK_PATH = path.join(
  os.tmpdir(),
  `nova-vite-start-api-${process.pid}.lock`,
);

describe('acquireLock / releaseLock', () => {
  beforeEach(() => {
    expect(TEST_LOCK_PATH).not.toBe(LOCK_PATH);
    fs.rmSync(TEST_LOCK_PATH, { force: true });
  });

  afterEach(() => {
    fs.rmSync(TEST_LOCK_PATH, { force: true });
  });

  it('coalesces a concurrent restart into exactly one holder', () => {
    // Simulates the manual "Start API" button racing browser auto-heal —
    // only one of the two POSTs may proceed at a time (see PROBLEM_LOG
    // 2026-07-23: unlocked concurrent restarts caused WinError 10048).
    expect(acquireLock(TEST_LOCK_PATH)).toBe(true);
    expect(fs.existsSync(TEST_LOCK_PATH)).toBe(true);
    expect(acquireLock(TEST_LOCK_PATH)).toBe(false);
    releaseLock(TEST_LOCK_PATH);
    expect(acquireLock(TEST_LOCK_PATH)).toBe(true);
    releaseLock(TEST_LOCK_PATH);
  });

  it('steals a stale lock left by a crashed process', () => {
    fs.mkdirSync(path.dirname(TEST_LOCK_PATH), { recursive: true });
    fs.writeFileSync(TEST_LOCK_PATH, JSON.stringify({ pid: 999999, ts: Date.now() - 120_000 }));
    expect(acquireLock(TEST_LOCK_PATH)).toBe(true);
    releaseLock(TEST_LOCK_PATH);
  });
});

describe('isLockStale', () => {
  it('is not stale when timestamp is recent', () => {
    const now = 1_000_000;
    const raw = JSON.stringify({ pid: 123, ts: now - 1000 });
    expect(isLockStale(raw, now, 60_000)).toBe(false);
  });

  it('is stale once the age exceeds the staleness window', () => {
    const now = 1_000_000;
    const raw = JSON.stringify({ pid: 123, ts: now - 61_000 });
    expect(isLockStale(raw, now, 60_000)).toBe(true);
  });

  it('treats unreadable JSON as stale (safe to steal)', () => {
    expect(isLockStale('not json', Date.now())).toBe(true);
  });

  it('treats a missing/non-numeric ts as stale', () => {
    expect(isLockStale(JSON.stringify({ pid: 1 }), Date.now())).toBe(true);
    expect(isLockStale(JSON.stringify({ pid: 1, ts: 'x' }), Date.now())).toBe(true);
  });
});
