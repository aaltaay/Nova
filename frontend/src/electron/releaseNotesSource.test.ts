/**
 * The notes the update notice fetched are what What's new reads after the
 * restart -- no second request, and nothing to fetch on a link that is down at
 * launch. A failed fetch says why and never throws.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RELEASE_NOTES_CACHE_FILE,
  cacheCovers,
  createNotesSource,
} from '../../electron/releaseNotesSource.mjs';

const row = (tag: string) => ({
  tag_name: tag,
  body: `<!-- nova-release-notes {"schema_version":1,"tag":"${tag}","title":"T ${tag}","summary":"S ${tag}.","points":[]} -->`,
  html_url: `https://github.com/aaltaay/Nova/releases/tag/${tag}`,
  published_at: '2026-09-23T20:00:00Z',
  draft: false,
  prerelease: false,
  assets: ['dropped from the cache'],
});
const logger = { info: vi.fn(), warn: vi.fn() };
let dir = '';

function source(fetch: ReturnType<typeof vi.fn>) {
  return createNotesSource({ fetch, dir: () => dir, logger, timeoutMs: 1_000 });
}

const answering = (rows: unknown) => vi.fn(async () => ({ ok: true, status: 200, json: async () => rows }));

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-notes-'));
});

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

describe('release notes source', () => {
  it('fetches once, keeps the page, and answers the next range from it', async () => {
    const fetch = answering([row('v980'), row('v978'), row('v975')]);
    const notes = source(fetch);
    const offer = await notes.load({ after: 'v975', through: 'v980' });
    expect(offer).toMatchObject({ loading: false, error: null, more: 0 });
    expect(offer.releases.map((r: { tag: string }) => r.tag)).toEqual(['v980', 'v978']);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(fetch.mock.calls[0][0])).toBe('https://api.github.com/repos/aaltaay/Nova/releases?per_page=100');
    const cached = JSON.parse(fs.readFileSync(path.join(dir, RELEASE_NOTES_CACHE_FILE), 'utf8'));
    expect(cached.schema_version).toBe(1);
    expect(cached.rows[0]).not.toHaveProperty('assets');
    // After the restart, a fresh source (a new process) reads the same page.
    const whatsNew = await source(fetch).load({ after: 'v975', through: 'v980' });
    expect(whatsNew.releases).toHaveLength(2);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('fetches again when the cache does not hold the release asked for', async () => {
    const fetch = answering([row('v981'), row('v980')]);
    fs.writeFileSync(path.join(dir, RELEASE_NOTES_CACHE_FILE), JSON.stringify({ schema_version: 1, rows: [row('v980')] }));
    const notes = await source(fetch).load({ after: 'v980', through: 'v981' });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(notes.releases.map((r: { tag: string }) => r.tag)).toEqual(['v981']);
  });

  it('says why when GitHub cannot be reached, and still answers from a cache that holds the release', async () => {
    const down = vi.fn(async () => {
      throw new Error('net::ERR_INTERNET_DISCONNECTED');
    });
    const none = await source(down).load({ after: 'v975', through: 'v980' });
    expect(none).toMatchObject({ loading: false, releases: [] });
    expect(none.error).toBe('Release notes could not be loaded: net::ERR_INTERNET_DISCONNECTED');
    expect(down).toHaveBeenCalledTimes(2); // one retry
    const refused = await source(vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) }))).load({
      through: 'v980',
    });
    expect(refused.error).toContain('HTTP 403');
  });

  it('ignores a cache of another schema version', async () => {
    fs.writeFileSync(path.join(dir, RELEASE_NOTES_CACHE_FILE), JSON.stringify({ schema_version: 9, rows: [row('v980')] }));
    const fetch = answering([row('v980')]);
    await source(fetch).load({ after: null, through: 'v980' });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('schema_version 9'));
  });

  it('trusts a cache only when it reaches back to the installed release', () => {
    const page = Array.from({ length: 100 }, (_, i) => row(`v${1000 - i}`));
    expect(cacheCovers(page, { after: 'v950', through: 'v1000' })).toBe(true);
    expect(cacheCovers(page, { after: 'v800', through: 'v1000' })).toBe(false);
    expect(cacheCovers([row('v980')], { after: 'v800', through: 'v980' })).toBe(true); // GitHub's whole list
    expect(cacheCovers([row('v980')], { after: null, through: 'v981' })).toBe(false);
  });
});
