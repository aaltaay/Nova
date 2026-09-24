/**
 * Help > File an Issue… goes to the desk's form when the page listens, else GitHub's page; the
 * form may open only this repository's issue pages and gists.
 */
import { describe, expect, it, vi } from 'vitest';
import { NEW_ISSUE_PAGE, createIssueRequest, isIssueLink } from '../../electron/issueLinks.mjs';

describe('issue links', () => {
  it.each([
    'https://github.com/aaltaay/Nova/issues/612',
    'https://github.com/aaltaay/Nova/issues/new?title=x&body=y&labels=bug',
    'https://github.com/aaltaay/Nova/issues/new/choose',
    'https://gist.github.com/aaltaay/0123456789abcdef0123',
  ])('opens %s', (url) => expect(isIssueLink(url)).toBe(true));

  it.each([
    'http://github.com/aaltaay/Nova/issues/612',
    'https://github.com/aaltaay/Other/issues/1',
    'https://github.com/aaltaay/Nova/pulls',
    'https://github.com.evil.example/aaltaay/Nova/issues/1',
    'https://user:pw@github.com/aaltaay/Nova/issues/1',
    'https://gist.github.com/aaltaay/not-a-gist',
    'javascript:alert(1)',
    '',
  ])('refuses %s', (url) => expect(isIssueLink(url)).toBe(false));
});

describe('Help > File an Issue…', () => {
  function setup(listening: boolean) {
    const bridge = { hasListener: () => listening, set: vi.fn() };
    const win = { isDestroyed: () => false, isMinimized: () => true, restore: vi.fn(), focus: vi.fn() };
    const openExternal = vi.fn(async () => undefined);
    const request = createIssueRequest({ bridge, getWindow: () => win, openExternal, now: () => 42,
      logger: { warn: vi.fn() } });
    return { bridge, win, openExternal, request };
  }

  it('opens the desk form and brings the window forward', () => {
    const { bridge, win, openExternal, request } = setup(true);
    expect(request()).toBe('desk');
    expect(bridge.set).toHaveBeenCalledWith('file_issue', { requested_at: 42 });
    expect(win.restore).toHaveBeenCalled();
    expect(win.focus).toHaveBeenCalled();
    expect(openExternal).not.toHaveBeenCalled();
  });

  it("falls back to GitHub's page when no desk page listens", () => {
    const { bridge, openExternal, request } = setup(false);
    expect(request()).toBe('browser');
    expect(openExternal).toHaveBeenCalledWith(NEW_ISSUE_PAGE);
    expect(bridge.set).not.toHaveBeenCalled();
  });
});
