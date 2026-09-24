/**
 * The desk reads release notes only from the record tools/release_notes.py
 * writes into each Release; a release without one is listed as unrecorded,
 * never given an invented summary.
 */
import { describe, expect, it } from 'vitest';
import {
  RELEASES_PER_PAGE,
  isReleaseLink,
  notesText,
  parseNotesRecord,
  releaseEntry,
  releaseNumber,
  selectReleases,
  tagNumber,
  whatsNewRange,
} from '../../electron/releaseNotes.mjs';

const record = (tag: string, extra: Record<string, unknown> = {}) =>
  `<!-- nova-release-notes ${JSON.stringify({
    schema_version: 1,
    tag,
    title: `Title ${tag}`,
    kind: 'fix',
    scope: 'sim',
    pr: 539,
    summary: `Summary ${tag}.`,
    points: ['one', 'two'],
    ...extra,
  })} -->`;

const row = (tag: string, body = record(tag)) => ({
  tag_name: tag,
  body: `## What's new in ${tag}\n\n${body}\n\n---\n\nNova ${tag} Windows desktop.`,
  html_url: `https://github.com/aaltaay/Nova/releases/tag/${tag}`,
  published_at: '2026-09-23T20:00:00Z',
  draft: false,
  prerelease: false,
});

describe('the release record', () => {
  it('reads what tools/release_notes.py writes, escapes included', () => {
    const body = record('v976', { summary: 'Keeps <b> and --> out.' }).replace('<b>', '\\u003cb\\u003e').replace('-->', '--\\u003e');
    expect(parseNotesRecord(`text\n${body}\nmore`)).toEqual({
      title: 'Title v976',
      kind: 'fix',
      scope: 'sim',
      pr: 539,
      summary: 'Keeps <b> and --> out.',
      points: ['one', 'two'],
    });
  });

  it('refuses a body without the record, broken JSON, or another schema version', () => {
    expect(parseNotesRecord('Nova v970 Windows desktop.')).toBeNull();
    expect(parseNotesRecord('<!-- nova-release-notes {not json} -->')).toBeNull();
    expect(parseNotesRecord(record('v976', { schema_version: 2 }))).toBeNull();
    expect(parseNotesRecord(undefined)).toBeNull();
  });

  it('lists a release made before release notes as unrecorded, with its own page', () => {
    const entry = releaseEntry(row('v970', 'Nova v970 Windows desktop.'));
    expect(entry).toMatchObject({ tag: 'v970', recorded: false, title: '', summary: '', points: [], pr_url: null });
    expect(entry?.url).toBe('https://github.com/aaltaay/Nova/releases/tag/v970');
    expect(releaseEntry({ ...row('v971'), draft: true })).toBeNull();
    expect(releaseEntry({ ...row('v971'), tag_name: 'nightly' })).toBeNull();
    expect(releaseEntry(row('v976'))?.pr_url).toBe('https://github.com/aaltaay/Nova/pull/539');
  });
});

describe('which releases', () => {
  const rows = [row('v980'), row('v978'), row('v977'), row('v975'), row('v972')];

  it('lists the releases after the installed one up to the target, newest first', () => {
    const picked = selectReleases(rows, { after: 'v975', through: 'v978' });
    expect(picked.releases.map((r: { tag: string }) => r.tag)).toEqual(['v978', 'v977']);
    expect(picked.more).toBe(0);
    expect(picked.older_unlisted).toBe(false);
  });

  it('counts what it does not list, and says when one page did not reach back far enough', () => {
    expect(selectReleases(rows, { after: null, through: 'v980', limit: 2 }).more).toBe(3);
    const fullPage = Array.from({ length: RELEASES_PER_PAGE }, (_, i) => row(`v${1100 - i}`));
    expect(selectReleases(fullPage, { after: 'v900', through: 'v1100' }).older_unlisted).toBe(true);
    expect(selectReleases(fullPage, { after: 'v1050', through: 'v1100' }).older_unlisted).toBe(false);
  });

  it("shows What's new once per update, and only the installed release the first time", () => {
    expect(whatsNewRange({ installed: 'v980', seen: 'v975' })).toEqual({ after: 'v975', through: 'v980', since: 'v975' });
    expect(whatsNewRange({ installed: 'v980', seen: null })).toEqual({ after: 'v979', through: 'v980', since: null });
    expect(whatsNewRange({ installed: 'v980', seen: 'v980' })).toBeNull();
    expect(whatsNewRange({ installed: 'v980', seen: 'v990' })).toBeNull();
    expect(whatsNewRange({ installed: '0.0.0-dev', seen: null })).toBeNull();
  });

  it('maps tags and app versions to one number', () => {
    expect(tagNumber('v976')).toBe(976);
    expect(tagNumber('976')).toBeNull();
    expect(releaseNumber('0.1.976')).toBe(976);
    expect(releaseNumber('v976')).toBe(976);
  });
});

describe('links and text', () => {
  it("opens only this repo's release and pull request pages", () => {
    expect(isReleaseLink('https://github.com/aaltaay/Nova/releases')).toBe(true);
    expect(isReleaseLink('https://github.com/aaltaay/Nova/releases/tag/v976')).toBe(true);
    expect(isReleaseLink('https://github.com/aaltaay/Nova/pull/540')).toBe(true);
    expect(isReleaseLink('https://github.com/aaltaay/Nova/pull/540/../../evil')).toBe(false);
    expect(isReleaseLink('https://github.com/someone/Nova/releases')).toBe(false);
    expect(isReleaseLink('http://github.com/aaltaay/Nova/releases')).toBe(false);
    expect(isReleaseLink('https://github.com.evil.example/aaltaay/Nova/releases')).toBe(false);
  });

  it('writes plain text for a dialog, cut to fit', () => {
    const { releases } = selectReleases([row('v977'), row('v976', 'none')], { after: 'v975', through: 'v977' });
    expect(notesText(releases)).toBe(
      'v977 -- Title v977\nSummary v977.\n  - one\n  - two\n\nv976 -- no release notes recorded',
    );
    expect(notesText(releases, { maxChars: 10 })).toHaveLength(10);
  });
});
