import { describe, expect, it } from 'vitest';
import { kindLabel, readUpdateView } from './updateView';

const notes = {
  loading: false,
  error: null,
  releases: [
    {
      tag: 'v976',
      recorded: true,
      title: 'Release notes after an update',
      kind: 'feat',
      scope: 'desktop',
      pr: 540,
      pr_url: 'https://github.com/aaltaay/Nova/pull/540',
      summary: 'Nova shows what changed.',
      points: ['one', 7, ''],
      url: 'https://github.com/aaltaay/Nova/releases/tag/v976',
    },
    { tag: 'not-a-tag' },
  ],
  more: 2,
  older_unlisted: false,
  page_url: 'https://github.com/aaltaay/Nova/releases',
};

describe('readUpdateView', () => {
  it('reads the notice and What\'s new the main process publishes', () => {
    const view = readUpdateView({
      schema_version: 1,
      installed: 'v975',
      notice: { stage: 'available', tag: 'v976', installed: 'v975', percent: 0, retry: 0, error: '', notes },
      whats_new: { mode: 'updated', tag: 'v975', since: 'v970', notes },
    });
    expect(view?.installed).toBe('v975');
    expect(view?.notice).toMatchObject({ stage: 'available', tag: 'v976' });
    expect(view?.notice?.notes?.releases).toEqual([
      {
        tag: 'v976',
        recorded: true,
        title: 'Release notes after an update',
        kind: 'feat',
        scope: 'desktop',
        pr: 540,
        prUrl: 'https://github.com/aaltaay/Nova/pull/540',
        summary: 'Nova shows what changed.',
        points: ['one'],
        url: 'https://github.com/aaltaay/Nova/releases/tag/v976',
      },
    ]);
    expect(view?.notice?.notes?.more).toBe(2);
    expect(view?.whatsNew).toMatchObject({ mode: 'updated', tag: 'v975', since: 'v970' });
  });

  it('reads nothing from another schema version or a malformed part', () => {
    expect(readUpdateView({ schema_version: 2, notice: null })).toBeNull();
    expect(readUpdateView(null)).toBeNull();
    const view = readUpdateView({
      schema_version: 1,
      installed: 'v975',
      notice: { stage: 'explode', tag: 'v976' },
      whats_new: { mode: 'updated', tag: 'v975' },
    });
    expect(view?.notice).toBeNull();
    expect(view?.whatsNew).toBeNull(); // no notes: nothing to show
  });

  it('labels a change by its kind', () => {
    expect(kindLabel('feat')).toBe('New');
    expect(kindLabel('fix')).toBe('Fix');
    expect(kindLabel('wip')).toBe('wip');
    expect(kindLabel(null)).toBe('');
  });
});
