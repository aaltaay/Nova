/**
 * One screen recording file (ADR 035): `close()` settles only once the file's
 * descriptor is closed, not when its last write is flushed (#927), so whoever
 * awaits it can move or delete the folder.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { SegmentFile } from '../../electron/screenRecordFiles.mjs';

let tmp = '';
beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-segment-'));
});
afterEach(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('SegmentFile', () => {
  it('closes the file before close() settles, with every byte written', async () => {
    const file = new SegmentFile(path.join(tmp, '2026-09-24', '094400-screen1.mkv'));
    file.write(Buffer.from([1, 2, 3]));
    file.write(Buffer.from([4]));
    expect(await file.close()).toBe(4);
    expect(file.stream.closed).toBe(true);
    expect([...fs.readFileSync(file.file)]).toEqual([1, 2, 3, 4]);
    fs.rmSync(path.join(tmp, '2026-09-24'), { recursive: true });
  });

  it('is one close however often it is asked', async () => {
    const file = new SegmentFile(path.join(tmp, '094400-screen1.mkv'));
    const first = file.close();
    expect(file.close()).toBe(first);
    expect(await first).toBe(0);
    expect(file.close()).toBe(first);
  });

  it('settles for a file that could not be opened, and keeps the reason', async () => {
    const taken = path.join(tmp, '094400-screen1.mkv');
    fs.writeFileSync(taken, 'x');
    const file = new SegmentFile(taken); // `wx`: never overwrites a recording
    expect(await file.close()).toBe(0);
    expect(file.stream.closed).toBe(true);
    expect(file.error).toMatch(/EEXIST/);
    expect(fs.readFileSync(taken, 'utf8')).toBe('x');
  });

  it('settles for a file already torn down', async () => {
    const file = new SegmentFile(path.join(tmp, '094400-screen1.mkv'));
    file.write(Buffer.from([1, 2]));
    file.stream.destroy();
    expect(await file.close()).toBe(2);
    expect(file.stream.closed).toBe(true);
  });
});
