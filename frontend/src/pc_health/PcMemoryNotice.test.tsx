/**
 * @vitest-environment jsdom
 *
 * The low-memory strip under the header (operator ask, 2026-10-15): it draws the backend's words, amber or red,
 * hides on Later until the backend's key changes, and draws nothing for an answer it cannot read. It never
 * takes focus and has no control that acts on a program. Process names are made up.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PcMemoryNotice } from './PcMemoryNotice';
import { hiddenByLater, parsePcMemoryNotice, type PcMemoryNoticeModel } from './memoryNoticeRead';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const LOW = {
  level: 'low',
  key: '1792082820|500',
  text: 'PC memory low: 8.9 GB of 96 GB free.',
  hint: 'Biggest: numbercruncher.exe, PID 500, holds 118.6 GB, running 3 min. Nova only warns: it never stops a program. Task Manager > Details, by PID.',
};

function answer(notice: unknown, init: { ok?: boolean; schema?: number } = {}) {
  return { ok: init.ok ?? true, json: async () => ({ schema_version: init.schema ?? 1, in_session: true, notice }) };
}

function fetchSequence(...answers: unknown[]) {
  const fn = vi.fn();
  for (const a of answers) fn.mockResolvedValueOnce(a);
  fn.mockResolvedValue(answers[answers.length - 1]);
  return fn;
}

describe('parsePcMemoryNotice', () => {
  it('reads a version 1 notice and nothing else', () => {
    expect(parsePcMemoryNotice({ schema_version: 1, notice: LOW })).toEqual(LOW);
    expect(parsePcMemoryNotice({ schema_version: 1, notice: null })).toBeNull();
    expect(parsePcMemoryNotice({ schema_version: 2, notice: LOW })).toBeNull();
    expect(parsePcMemoryNotice({ schema_version: 1, notice: { ...LOW, level: 'fine' } })).toBeNull();
    expect(parsePcMemoryNotice({ schema_version: 1, notice: { ...LOW, text: '' } })).toBeNull();
    expect(parsePcMemoryNotice({ schema_version: 1, notice: { ...LOW, key: 7 } })).toBeNull();
    expect(parsePcMemoryNotice('nope')).toBeNull();
  });
});

describe('hiddenByLater', () => {
  const at = (level: PcMemoryNoticeModel['level'], key = '1|500'): PcMemoryNoticeModel => ({ ...LOW, key, level });

  it('hides the same episode and process at the same level or better, never worse or another key', () => {
    expect(hiddenByLater(at('low'), null)).toBe(false);
    expect(hiddenByLater(at('easing'), { key: '1|500', level: 'low' })).toBe(true);
    expect(hiddenByLater(at('low'), { key: '1|500', level: 'easing' })).toBe(true);
    expect(hiddenByLater(at('nearly_out'), { key: '1|500', level: 'low' })).toBe(false);
    expect(hiddenByLater(at('low'), { key: '1|500', level: 'nearly_out' })).toBe(true);
    expect(hiddenByLater(at('low', '1|600'), { key: '1|500', level: 'nearly_out' })).toBe(false);
  });
});

describe('PcMemoryNotice', () => {
  it("draws the backend's words, names the process and reads the notice route", async () => {
    const fetchImpl = fetchSequence(answer(LOW));
    render(<PcMemoryNotice fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={60_000} />);
    const strip = await screen.findByTestId('pc-memory-notice');
    expect(strip.textContent).toContain('PC memory low: 8.9 GB of 96 GB free.');
    expect(strip.textContent).toContain('numbercruncher.exe, PID 500, holds 118.6 GB, running 3 min');
    expect(strip.getAttribute('data-level')).toBe('low');
    expect(strip.getAttribute('role')).toBe('status');
    expect(String(fetchImpl.mock.calls[0]?.[0])).toMatch(/\/api\/perf\/memory-notice$/);
  });

  it('is red when nearly out, and only Later is a control', async () => {
    const fetchImpl = fetchSequence(answer({ ...LOW, level: 'nearly_out', key: '1792082820|500' }));
    render(<PcMemoryNotice fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={60_000} />);
    const strip = await screen.findByTestId('pc-memory-notice');
    expect(strip.getAttribute('data-level')).toBe('nearly_out');
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Later']);
    expect(strip.contains(document.activeElement)).toBe(false);          // it never takes focus
  });

  it('draws nothing without a notice, for an answer it cannot read, or a backend without the route', async () => {
    for (const reply of [answer(null), answer(LOW, { schema: 2 }), answer(LOW, { ok: false })]) {
      const fetchImpl = fetchSequence(reply);
      const { container, unmount } = render(<PcMemoryNotice fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={60_000} />);
      await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
      await act(async () => {});
      expect(container.querySelector('[data-testid="pc-memory-notice"]')).toBeNull();
      unmount();
    }
    const failing = vi.fn().mockRejectedValue(new Error('backend down'));
    const { container } = render(<PcMemoryNotice fetchImpl={failing as unknown as typeof fetch} pollMs={60_000} />);
    await waitFor(() => expect(failing).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="pc-memory-notice"]')).toBeNull();
  });

  it('Later holds while the key does and it gets no worse; worse, or another key, brings it back', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const easing = { ...LOW, level: 'easing', text: 'PC memory was low 2 min ago: 34.6 GB of 96 GB free now.' };
    const nearly = { ...LOW, level: 'nearly_out', text: 'PC memory nearly out: 0.1 GB of 96 GB free, 182 of 188 GB committed.' };
    const other = { ...LOW, key: '1792082820|600' };
    const fetchImpl = fetchSequence(answer(LOW), answer(easing), answer(nearly), answer(LOW), answer(other));
    render(<PcMemoryNotice fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={1_000} />);
    const tick = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(1_000); }); };
    fireEvent.click(await screen.findByRole('button', { name: 'Later' }));
    expect(screen.queryByTestId('pc-memory-notice')).toBeNull();
    await tick();                                                            // easing: no worse, still hidden
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId('pc-memory-notice')).toBeNull();
    await tick();                                                            // nearly out: worse, back
    expect((await screen.findByTestId('pc-memory-notice')).getAttribute('data-level')).toBe('nearly_out');
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await tick();                                                            // low again: hidden at nearly out
    expect(fetchImpl).toHaveBeenCalledTimes(4);
    expect(screen.queryByTestId('pc-memory-notice')).toBeNull();
    await tick();                                                            // another biggest process: back
    expect((await screen.findByTestId('pc-memory-notice')).getAttribute('data-level')).toBe('low');
  });

  it('gives up a read the backend never answers, keeps the strip, and reads again on time', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(answer(LOW))
      .mockImplementationOnce((_url: unknown, init?: RequestInit) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('The read was given up', 'AbortError')));
      }))
      .mockResolvedValue(answer(null));
    render(<PcMemoryNotice fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={1_000} timeoutMs={300} />);
    await screen.findByTestId('pc-memory-notice');
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });  // the second read hangs
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });    // given up: the strip stays
    expect((fetchImpl.mock.calls[1]?.[1] as RequestInit).signal?.aborted).toBe(true);
    expect(screen.getByTestId('pc-memory-notice').getAttribute('data-level')).toBe('low');
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });    // the next read runs on time
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(screen.queryByTestId('pc-memory-notice')).toBeNull();
  });

  it('goes by itself when the backend has no notice any more', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchImpl = fetchSequence(answer(LOW), answer(null));
    render(<PcMemoryNotice fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={1_000} />);
    await screen.findByTestId('pc-memory-notice');
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(screen.queryByTestId('pc-memory-notice')).toBeNull();
  });
});
