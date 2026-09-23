/**
 * The resumable installer download (#347, 2026-09-23): a link that drops a TLS
 * record every few dozen MB must still deliver the installer, keep what arrived
 * across failures, never hand over a file that fails the release checksum, and
 * leave it exactly where electron-updater's own cache check accepts it.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  PARTIAL_DIR_NAME,
  downloadInstaller,
  installerTarget,
  nextRange,
  parseContentRange,
  retryDelay,
  retryWhileBusy,
  UPDATE_CHUNK_RETRY_DELAYS_MS,
} from '../../electron/updateDownload.mjs';

const CHUNK = 1000;
const FILE_NAME = 'Nova-Setup-v961.exe';
const URL_HREF = `https://github.com/aaltaay/Nova/releases/download/v961/${FILE_NAME}`;

function sha512(buf: Buffer) {
  return crypto.createHash('sha512').update(buf).digest('base64');
}

function makeTarget(body: Buffer, overrides: Record<string, unknown> = {}) {
  return {
    url: URL_HREF,
    fileName: FILE_NAME,
    sha512: sha512(body),
    size: body.length,
    isAdminRightsRequired: false,
    version: '0.1.961',
    ...overrides,
  };
}

type Reply = { status: number; headers: { get: (k: string) => string | null }; arrayBuffer: () => Promise<ArrayBuffer> };

/** A Range-honouring server; `failAt` maps a range start to how many times it errors first. */
function fakeServer(body: Buffer, failAt: Record<number, number> = {}) {
  const asked: string[] = [];
  const fetch = vi.fn(async (_url: string, init: { headers: Record<string, string> }): Promise<Reply> => {
    const range = init.headers.Range;
    asked.push(range);
    const [start, end] = /bytes=(\d+)-(\d+)/.exec(range)!.slice(1).map(Number);
    if ((failAt[start] ?? 0) > 0) {
      failAt[start] -= 1;
      throw new Error('net::ERR_SSL_PROTOCOL_ERROR');
    }
    const slice = body.subarray(start, end + 1);
    return {
      status: 206,
      headers: { get: (k) => (k.toLowerCase() === 'content-range' ? `bytes ${start}-${end}/${body.length}` : null) },
      arrayBuffer: async () => slice.buffer.slice(slice.byteOffset, slice.byteOffset + slice.length),
    };
  });
  return { fetch, asked };
}

const logger = { info: vi.fn(), warn: vi.fn() };
let cacheDir = '';

beforeEach(() => {
  cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-update-dl-'));
});

afterEach(() => {
  fs.rmSync(cacheDir, { recursive: true, force: true });
});

function run(target: ReturnType<typeof makeTarget>, fetch: unknown, extra: Record<string, unknown> = {}) {
  return downloadInstaller({ target, cacheDir, fetch, logger, sleep: async () => {}, chunkBytes: CHUNK, ...extra } as never);
}

describe('pure helpers', () => {
  it('plans inclusive chunk ranges and stops at the end', () => {
    expect(nextRange(0, 2500, 1000)).toEqual({ start: 0, end: 999 });
    expect(nextRange(2000, 2500, 1000)).toEqual({ start: 2000, end: 2499 });
    expect(nextRange(2500, 2500, 1000)).toBeNull();
  });

  it('reads Content-Range and rejects anything else', () => {
    expect(parseContentRange('bytes 0-99/1000')).toEqual({ start: 0, end: 99, total: 1000 });
    expect(parseContentRange('bytes */1000')).toBeNull();
    expect(parseContentRange(null)).toBeNull();
  });

  it('spends a bounded retry budget per chunk', () => {
    expect(retryDelay(1)).toBe(UPDATE_CHUNK_RETRY_DELAYS_MS[0]);
    expect(retryDelay(UPDATE_CHUNK_RETRY_DELAYS_MS.length)).toBe(UPDATE_CHUNK_RETRY_DELAYS_MS.at(-1));
    expect(retryDelay(UPDATE_CHUNK_RETRY_DELAYS_MS.length + 1)).toBeNull();
  });

  it('waits out a sharing lock, but not any other error or a lock that never lifts', async () => {
    const sleep = vi.fn(async () => {});
    const busy = Object.assign(new Error('EBUSY: resource busy or locked'), { code: 'EBUSY' });
    let calls = 0;
    await expect(
      retryWhileBusy(async () => {
        calls += 1;
        if (calls < 3) throw busy;
        return 'done';
      }, sleep),
    ).resolves.toBe('done');
    expect(sleep).toHaveBeenCalledTimes(2);

    const missing = Object.assign(new Error('ENOENT'), { code: 'ENOENT' });
    await expect(retryWhileBusy(async () => Promise.reject(missing), sleep)).rejects.toBe(missing);
    await expect(retryWhileBusy(async () => Promise.reject(busy), sleep, 4)).rejects.toBe(busy);
  });

  it('picks the .exe electron-updater would fetch, named as its cache names it', () => {
    const files = [
      { url: new URL('https://x/y/app.blockmap'), info: { sha512: 'b', size: 1 } },
      { url: new URL(URL_HREF), info: { sha512: 'abc', size: 150_537_712 } },
    ];
    expect(installerTarget(files, '0.1.961')).toMatchObject({
      url: URL_HREF,
      fileName: FILE_NAME,
      sha512: 'abc',
      size: 150_537_712,
      isAdminRightsRequired: false,
    });
  });

  it('refuses a target it cannot check or resume', () => {
    expect(installerTarget([{ url: new URL(URL_HREF), info: { size: 10 } }], '1')).toBeNull();
    expect(installerTarget([{ url: new URL(URL_HREF), info: { sha512: 'a' } }], '1')).toBeNull();
    expect(installerTarget(undefined as never, '1')).toBeNull();
  });
});

describe('downloadInstaller', () => {
  const body = crypto.randomBytes(4_500);

  it('rides out dropped chunks and leaves a verified installer in the pending cache', async () => {
    const { fetch } = fakeServer(body, { 1000: 2, 3000: 1 });
    const onRetry = vi.fn();
    const onProgress = vi.fn();
    const file = await run(makeTarget(body), fetch, { onRetry, onProgress });

    expect(file).toBe(path.join(cacheDir, 'pending', FILE_NAME));
    expect(fs.readFileSync(file).equals(body)).toBe(true);
    expect(JSON.parse(fs.readFileSync(path.join(cacheDir, 'pending', 'update-info.json'), 'utf8'))).toEqual({
      fileName: FILE_NAME,
      sha512: sha512(body),
      isAdminRightsRequired: false,
    });
    expect(onRetry.mock.calls.map(([r]) => r.attempt)).toEqual([1, 2, 1]);
    expect(onProgress).toHaveBeenLastCalledWith(100);
    // Nothing partial is left behind once handed off.
    expect(fs.readdirSync(path.join(cacheDir, PARTIAL_DIR_NAME))).toEqual([]);
  });

  it('keeps what arrived when a chunk exhausts its retries, and resumes from there', async () => {
    const first = fakeServer(body, { 2000: UPDATE_CHUNK_RETRY_DELAYS_MS.length + 1 });
    await expect(run(makeTarget(body), first.fetch)).rejects.toThrow(/gave up on bytes 2000-2999; 2000 kept/);

    const second = fakeServer(body);
    const file = await run(makeTarget(body), second.fetch);
    expect(second.asked).toEqual(['bytes=2000-2999', 'bytes=3000-3999', 'bytes=4000-4499']);
    expect(fs.readFileSync(file).equals(body)).toBe(true);
  });

  it('does not fetch again an installer already handed off (Later, then a restart)', async () => {
    const first = fakeServer(body);
    const file = await run(makeTarget(body), first.fetch);
    const second = fakeServer(body);
    await expect(run(makeTarget(body), second.fetch)).resolves.toBe(file);
    expect(second.fetch).not.toHaveBeenCalled();
    // A newer release is still downloaded.
    const newer = crypto.randomBytes(1_200);
    const third = fakeServer(newer);
    await run(makeTarget(newer, { fileName: 'Nova-Setup-v962.exe' }), third.fetch);
    expect(third.fetch).toHaveBeenCalled();
  });

  it('starts over when a newer release replaces the one partly downloaded', async () => {
    const first = fakeServer(body, { 2000: UPDATE_CHUNK_RETRY_DELAYS_MS.length + 1 });
    await expect(run(makeTarget(body), first.fetch)).rejects.toThrow();

    const newer = crypto.randomBytes(3_000);
    const second = fakeServer(newer);
    const file = await run(makeTarget(newer, { version: '0.1.962' }), second.fetch);
    expect(second.asked[0]).toBe('bytes=0-999');
    expect(fs.readFileSync(file).equals(newer)).toBe(true);
  });

  it('never hands over bytes that fail the release checksum', async () => {
    const tampered = Buffer.from(body);
    tampered[10] ^= 0xff;
    const { fetch } = fakeServer(tampered);
    await expect(run(makeTarget(body), fetch)).rejects.toThrow(/does not match the release checksum/);
    expect(fs.existsSync(path.join(cacheDir, 'pending'))).toBe(false);
    expect(fs.readdirSync(path.join(cacheDir, PARTIAL_DIR_NAME))).toEqual([]);
  });

  it('gives up at once on a release file that is gone', async () => {
    const fetch = vi.fn(async () => ({ status: 404, headers: { get: () => null }, arrayBuffer: async () => new ArrayBuffer(0) }));
    await expect(run(makeTarget(body), fetch)).rejects.toThrow(/HTTP 404/);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retries a server error instead of giving up', async () => {
    const good = fakeServer(body);
    let calls = 0;
    const fetch = vi.fn(async (url: string, init: { headers: Record<string, string> }) => {
      calls += 1;
      if (calls === 1) return { status: 503, headers: { get: () => null }, arrayBuffer: async () => new ArrayBuffer(0) };
      return good.fetch(url, init);
    });
    const file = await run(makeTarget(body), fetch);
    expect(fs.readFileSync(file).equals(body)).toBe(true);
  });

  it("is accepted by electron-updater's own cache check (contract pin)", async () => {
    const { fetch } = fakeServer(body);
    const target = makeTarget(body);
    const file = await run(target, fetch);

    const require = createRequire(import.meta.url);
    const { DownloadedUpdateHelper } = require('electron-updater/out/DownloadedUpdateHelper');
    const helper = new DownloadedUpdateHelper(cacheDir);
    const updateInfo = { version: target.version, files: [{ url: FILE_NAME, sha512: target.sha512, size: target.size }] };
    const fileInfo = { url: new URL(URL_HREF), info: updateInfo.files[0] };
    const cached = await helper.validateDownloadedPath(file, updateInfo, fileInfo, { info: vi.fn(), warn: vi.fn() });
    expect(cached).toBe(file);
  });
});
