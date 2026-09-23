/**
 * @vitest-environment jsdom
 *
 * ADR 018 -- the padlock drives a backend latch, not a per-tab flag. Live
 * arming carries the PIN to the backend; the client never judges it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DESK_ARM_NO_ANSWER_MESSAGE } from '../constants';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  refresh: vi.fn(),
  sample: false,
}));

vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('./ibkrStatusPoller', () => ({ refreshIbkrStatusNow: mocks.refresh }));
vi.mock('../sample_data/sampleOrderGuard', () => ({ onSampleDesk: () => mocks.sample }));

import { armDesk } from './armDesk';

function answer(status: number, body?: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new SyntaxError('no body');
      return body;
    },
  };
}

function sentBody(call = 0) {
  return JSON.parse(mocks.fetch.mock.calls[call][1].body);
}

describe('armDesk', () => {
  beforeEach(() => {
    mocks.fetch.mockReset();
    mocks.refresh.mockReset();
    mocks.sample = false;
  });

  it('posts the requested latch state to the backend as the operator', async () => {
    mocks.fetch.mockResolvedValue(answer(200, { armed: true }));
    await expect(armDesk(true)).resolves.toEqual({ ok: true, code: null, message: null });

    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = mocks.fetch.mock.calls[0];
    expect(String(url)).toContain('/api/ibkr/arm');
    expect(init.method).toBe('POST');
    expect(sentBody()).toEqual({ armed: true, actor: 'operator' });
  });

  it('carries the Live PIN to the backend only when arming', async () => {
    mocks.fetch.mockResolvedValue(answer(200, {}));
    await armDesk(true, '135790');
    expect(sentBody(0)).toEqual({ armed: true, actor: 'operator', pin: '135790' });
    await armDesk(false, '135790');
    expect(sentBody(1)).toEqual({ armed: false, actor: 'operator' });
  });

  it("returns the backend's 403 detail and code as-is", async () => {
    mocks.fetch.mockResolvedValue(answer(403, {
      detail: 'Live PIN is not set -- run py -3 tools/set_live_arm_pin.py',
      code: 'ARM_PIN_NOT_SET',
    }));
    await expect(armDesk(true, '000000')).resolves.toEqual({
      ok: false,
      code: 'ARM_PIN_NOT_SET',
      message: 'Live PIN is not set -- run py -3 tools/set_live_arm_pin.py',
    });
  });

  it('states a refusal with no readable body instead of assuming success', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mocks.fetch.mockResolvedValue(answer(500));
    const res = await armDesk(true);
    expect(res.ok).toBe(false);
    expect(res.code).toBeNull();
    expect(res.message).toMatch(/HTTP 500/);
    warn.mockRestore();
  });

  it('never throws when the backend is unreachable', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mocks.fetch.mockRejectedValue(new Error('backend down'));
    await expect(armDesk(true)).resolves.toEqual({
      ok: false, code: null, message: DESK_ARM_NO_ANSWER_MESSAGE,
    });
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('re-reads status either way, so the padlock cannot drift from the server', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mocks.fetch.mockRejectedValue(new Error('backend down'));
    await armDesk(false);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it('refuses on the sample desk without a request', async () => {
    mocks.sample = true;
    const res = await armDesk(true);
    expect(res.ok).toBe(false);
    expect(res.message).toMatch(/sample/i);
    expect(mocks.fetch).not.toHaveBeenCalled();
  });
});
