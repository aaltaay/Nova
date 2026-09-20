/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SimPlaybackButton } from './SimPlaybackButton';
import { API_BASE_URL } from '../constants';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
beforeEach(() => { mocks.fetch.mockReset(); });
afterEach(cleanup);

it.each([true, false])('toggles paused=%s and publishes the returned clock', async paused => {
  const returned = { sim: true, paused: !paused, minute_from_open: 12 };
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => returned });
  const onClock = vi.fn();
  render(<SimPlaybackButton clock={{ sim: true, paused }} onClock={onClock} />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: paused ? 'Play Sim time' : 'Pause Sim time' })); });
  expect(mocks.fetch).toHaveBeenCalledExactlyOnceWith(`${API_BASE_URL}/api/sim/clock`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paused: !paused }), signal: expect.any(AbortSignal),
  });
  expect(onClock).toHaveBeenCalledExactlyOnceWith(returned);
});

it.each([null, { sim: false, paused: false }])('cannot change playback outside a known Sim clock: %j', clock => {
  render(<SimPlaybackButton clock={clock} onClock={vi.fn()} />);
  const button = screen.getByRole('button');
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(button);
  expect(mocks.fetch).not.toHaveBeenCalled();
});

it('prevents duplicate requests while playback is changing', async () => {
  let resolve!: (value: unknown) => void;
  mocks.fetch.mockImplementation(() => new Promise(done => { resolve = done; }));
  render(<SimPlaybackButton clock={{ sim: true, paused: true }} onClock={vi.fn()} />);
  const button = screen.getByRole('button');
  fireEvent.click(button);
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(button);
  expect(mocks.fetch).toHaveBeenCalledTimes(1);
  await act(async () => { resolve({ ok: true, json: async () => ({ sim: true, paused: false }) }); });
  expect((button as HTMLButtonElement).disabled).toBe(false);
});

it.each([
  [() => Promise.resolve({ ok: false }), 'Could not change Sim playback. Try again.'],
  [() => Promise.reject(new Error('Connection interrupted')), 'Connection interrupted'],
] as const)('shows playback failures and clears them on retry', async (failure, message) => {
  mocks.fetch.mockImplementationOnce(failure);
  const onClock = vi.fn();
  render(<SimPlaybackButton clock={{ sim: true, paused: true }} onClock={onClock} />);
  await act(async () => { fireEvent.click(screen.getByRole('button')); });
  expect(screen.getByRole('alert').textContent).toBe(message);
  expect(onClock).not.toHaveBeenCalled();
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ sim: true, paused: false }) });
  await act(async () => { fireEvent.click(screen.getByRole('button')); });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(onClock).toHaveBeenCalledTimes(1);
});
