/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { initialView, withDisconnect, withServerBack, withServerCode, type CodeState } from './holdModel';
import { createHoldStore } from './installReloadHold';
import { PendingCodeNotice } from './PendingCodeNotice';

afterEach(() => cleanup());

const running = { boot: 'b1', seq: 0, head: 'aaa1111' };

const code = (over: Partial<CodeState> = {}): CodeState => ({
  schema_version: 1,
  boot: 'b1',
  seq: 2,
  head: 'bbb2222',
  at: '',
  recent: [
    { seq: 2, kind: 'source', file: 'src/chart/barsStore.ts' },
    { seq: 1, kind: 'html', file: 'index.html' },
  ],
  ...over,
});

function setup() {
  const store = createHoldStore(initialView(running));
  const reload = vi.fn();
  render(<PendingCodeNotice store={store} reload={reload} />);
  return { store, reload };
}

describe('PendingCodeNotice', () => {
  it('shows nothing while the page runs the code on disk', () => {
    setup();
    expect(screen.queryByTestId('dev-reload-notice')).toBeNull();
    expect(screen.queryByTestId('dev-reload-chip')).toBeNull();
  });

  it('says what changed and which revision each side is on, and reloads only on Reload', () => {
    const { store, reload } = setup();
    act(() => store.update((v) => withServerCode(v, code())));
    const notice = screen.getByTestId('dev-reload-notice');
    expect(notice.textContent).toContain('New code is on disk (2 changes).');
    expect(notice.textContent).toContain('Changed: src/chart/barsStore.ts, index.html.');
    expect(notice.textContent).toContain('This page runs aaa1111; the checkout is at bbb2222.');
    expect(reload).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('Later folds it into a chip that opens it again; nothing reloads', () => {
    const { store, reload } = setup();
    act(() => store.update((v) => withServerCode(v, code())));
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    expect(screen.queryByTestId('dev-reload-notice')).toBeNull();
    // More code arriving while folded does not pop it open or apply anything.
    act(() => store.update((v) => withServerCode(v, code({ seq: 3 }))));
    fireEvent.click(screen.getByTestId('dev-reload-chip'));
    expect(screen.getByTestId('dev-reload-notice').textContent).toContain('3 changes');
    expect(reload).not.toHaveBeenCalled();
  });

  it('says the dev server stopped, then that it restarted', () => {
    const { store } = setup();
    act(() => store.update(withDisconnect));
    expect(screen.getByTestId('dev-reload-notice').textContent).toContain('The dev server stopped.');
    act(() => store.update((v) => withServerBack(v, { boot: 'b2', seq: 0, head: 'ccc3333' })));
    const notice = screen.getByTestId('dev-reload-notice');
    expect(notice.textContent).toContain('The dev server restarted with the code on disk.');
    expect(notice.textContent).toContain('the checkout is at ccc3333');
  });

  it('never takes keyboard focus from the desk', () => {
    const { store } = setup();
    act(() => store.update((v) => withServerCode(v, code())));
    const later = screen.getByRole('button', { name: 'Later' });
    const ev = new MouseEvent('mousedown', { bubbles: true, cancelable: true });
    later.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
  });
});
