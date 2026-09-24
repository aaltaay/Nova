/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DesktopUpdateHost } from './DesktopUpdateHost';
import type { DesktopUpdatesBridge } from './useDesktopUpdate';

afterEach(() => cleanup());

const notes = (tags: string[], extra: Record<string, unknown> = {}) => ({
  loading: false,
  error: null,
  releases: tags.map((tag) => ({
    tag,
    recorded: true,
    title: `Title ${tag}`,
    kind: 'feat',
    scope: 'desk',
    pr: 540,
    pr_url: 'https://github.com/aaltaay/Nova/pull/540',
    summary: `Summary ${tag}.`,
    points: [`Point ${tag}`],
    url: `https://github.com/aaltaay/Nova/releases/tag/${tag}`,
  })),
  more: 0,
  older_unlisted: false,
  page_url: 'https://github.com/aaltaay/Nova/releases',
  ...extra,
});

const notice = (stage: string, extra: Record<string, unknown> = {}) => ({
  stage,
  tag: 'v977',
  installed: 'v975',
  percent: 0,
  retry: 0,
  error: '',
  notes: notes(['v977', 'v976']),
  ...extra,
});

function fakeBridge() {
  let push: (view: unknown) => void = () => {};
  const bridge: DesktopUpdatesBridge & { unsubscribe: ReturnType<typeof vi.fn> } = {
    unsubscribe: vi.fn(),
    subscribe: vi.fn((onView: (view: unknown) => void) => {
      push = onView;
      return bridge.unsubscribe;
    }),
    act: vi.fn(async () => ({ ok: true })),
  };
  const send = (view: Record<string, unknown>) =>
    act(() => push({ schema_version: 1, installed: 'v975', notice: null, whats_new: null, ...view }));
  return { bridge, send };
}

describe('the update notice', () => {
  it('says a newer Nova is out and asks: Update or Later', () => {
    const { bridge, send } = fakeBridge();
    render(<DesktopUpdateHost bridge={bridge} />);
    send({ notice: notice('available') });
    const bar = screen.getByTestId('update-notice');
    expect(bar.textContent).toContain('Nova v977 is available — you have v975.');
    expect(bar.textContent).toContain('Nova restarts only when you choose Restart to update');
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));
    expect(bridge.act).toHaveBeenLastCalledWith({ action: 'download' });
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    expect(bridge.act).toHaveBeenLastCalledWith({ action: 'later' });
  });

  it('opens what the update would bring, newest first, without touching the desk', () => {
    const { bridge, send } = fakeBridge();
    render(<DesktopUpdateHost bridge={bridge} />);
    send({ notice: notice('available') });
    expect(screen.queryAllByTestId('release-note')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: "What's new (2)" }));
    const listed = screen.getAllByTestId('release-note');
    expect(listed.map((li) => li.textContent?.slice(0, 4))).toEqual(['v977', 'v976']);
    expect(listed[0].textContent).toContain('New');
    expect(listed[0].textContent).toContain('Summary v977.');
    expect(listed[0].textContent).toContain('Point v977');
    fireEvent.click(screen.getAllByRole('button', { name: 'Pull request #540' })[0]);
    expect(bridge.act).toHaveBeenLastCalledWith({ action: 'open-link', url: 'https://github.com/aaltaay/Nova/pull/540' });
  });

  it('follows the download to Restart to update', () => {
    const { bridge, send } = fakeBridge();
    render(<DesktopUpdateHost bridge={bridge} />);
    send({ notice: notice('downloading', { percent: 42, retry: 2 }) });
    expect(screen.getByTestId('update-notice').textContent).toContain(
      'Downloading Nova v977… 42% — connection dropped, retrying (attempt 2).',
    );
    expect(screen.queryByRole('button', { name: 'Update' })).toBeNull();
    send({ notice: notice('stopped', { percent: 45, error: 'net::ERR_SSL_PROTOCOL_ERROR' }) });
    expect(screen.getByTestId('update-notice').textContent).toContain('stopped at 45%: net::ERR_SSL_PROTOCOL_ERROR');
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(bridge.act).toHaveBeenLastCalledWith({ action: 'download' });
    send({ notice: notice('ready', { percent: 100 }) });
    expect(screen.getByTestId('update-notice').textContent).toContain('Nova v977 is ready to install.');
    fireEvent.click(screen.getByRole('button', { name: 'Restart to update' }));
    expect(bridge.act).toHaveBeenLastCalledWith({ action: 'restart' });
    send({ notice: notice('installing') });
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    send({ notice: null });
    expect(screen.queryByTestId('update-notice')).toBeNull();
  });

  it('never takes keyboard focus from the desk', () => {
    const { bridge, send } = fakeBridge();
    render(
      <>
        <input aria-label="desk" />
        <DesktopUpdateHost bridge={bridge} />
      </>,
    );
    const desk = screen.getByLabelText('desk');
    desk.focus();
    send({ notice: notice('available'), whats_new: { mode: 'updated', tag: 'v975', since: 'v970', notes: notes(['v975']) } });
    expect(document.activeElement).toBe(desk);
  });
});

describe("What's new", () => {
  it('shows what the update brought and closes for good on Got it', () => {
    const { bridge, send } = fakeBridge();
    render(<DesktopUpdateHost bridge={bridge} />);
    send({ whats_new: { mode: 'updated', tag: 'v977', since: 'v975', notes: notes(['v977', 'v976']) } });
    const card = screen.getByTestId('whats-new');
    expect(card.textContent).toContain("What's new in Nova v977");
    expect(card.textContent).toContain('Updated from v975 — 2 releases.');
    expect(screen.getAllByTestId('release-note')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(bridge.act).toHaveBeenLastCalledWith({ action: 'whats-new-close' });
  });

  it('says so while loading, when notes could not be loaded, and for a release without notes', () => {
    const { bridge, send } = fakeBridge();
    render(<DesktopUpdateHost bridge={bridge} />);
    send({ whats_new: { mode: 'updated', tag: 'v977', since: null, notes: notes([], { loading: true }) } });
    expect(screen.getByTestId('whats-new').textContent).toContain('Loading release notes…');
    send({
      whats_new: {
        mode: 'updated',
        tag: 'v977',
        since: null,
        notes: notes([], { error: 'Release notes could not be loaded: net::ERR_INTERNET_DISCONNECTED' }),
      },
    });
    expect(screen.getByTestId('whats-new').textContent).toContain('net::ERR_INTERNET_DISCONNECTED');
    const unrecorded = notes(['v970']);
    unrecorded.releases[0] = { ...unrecorded.releases[0], recorded: false, title: '', summary: '', points: [] };
    send({ whats_new: { mode: 'recent', tag: 'v977', since: null, notes: unrecorded } });
    expect(screen.getByTestId('whats-new').textContent).toContain('No release notes were recorded for this release.');
    expect(screen.getByTestId('whats-new').textContent).toContain('The latest releases up to this version.');
  });
});

describe('outside the desktop app', () => {
  it('renders nothing without a bridge, and unsubscribes on unmount', () => {
    const { container } = render(<DesktopUpdateHost bridge={null} />);
    expect(container.innerHTML).toBe('');
    const { bridge } = fakeBridge();
    const { unmount } = render(<DesktopUpdateHost bridge={bridge} />);
    expect(bridge.subscribe).toHaveBeenCalledTimes(1);
    unmount();
    expect(bridge.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
