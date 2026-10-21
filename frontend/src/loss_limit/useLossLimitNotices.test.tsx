/**
 * @vitest-environment jsdom
 *
 * The loss limit's notices in every window, said out loud once (ADR 056): the window that reads
 * `GET /api/loss-limit` speaks; a window that follows its share only shows.
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LossLimitView } from './lossLimitApi';
import { resetLossLimitNoticesForTests } from './lossLimitNotices';
import { useLossLimitNotices } from './useLossLimitNotices';

const share = vi.hoisted(() => ({
  leader: true,
  snap: null as null | { ts: number; payload: unknown },
  published: [] as unknown[],
}));
vi.mock('../ibkr', () => ({
  claimDeskPollLeader: () => share.leader,
  publishDeskPollSnap: (_name: string, payload: unknown) => { share.published.push(payload); },
  readDeskPollSnap: () => share.snap,
  subscribeDeskPollSnap: () => () => {},
}));
const voice = vi.hoisted(() => ({ speakDesk: vi.fn() }));
vi.mock('../sound', () => voice);
const api = vi.hoisted(() => ({ fetchLossLimit: vi.fn() }));
vi.mock('./lossLimitApi', () => api);

const NOW = Date.now() / 1000;

function tripped(): LossLimitView {
  return {
    schema_version: 2,
    settings: { limit_usd: 2000, you_usd: null, bots_usd: null, warn: true, no_new_buys: true, auto_sell: false,
      set_at: null, source: 'operator', error: null },
    day: '2026-10-15', until: NOW + 3600, error: null,
    accounts: {
      paper: {
        name: 'Paper', counted_at: NOW, pnl: -2040, loss: 2040, unknown: null,
        lines: {
          account: {
            on: true, pnl: -2040, loss: 2040, warned_at: null, warned_loss: null, tripped_at: NOW - 5,
            tripped_loss: 2040, limit_usd: 2000, sold: null, sell_error: null, no_new_buys: null,
          },
        },
      },
    },
  };
}

function Host({ push }: { push: (n: unknown) => unknown }) {
  useLossLimitNotices(push);
  return null;
}

async function mount(push: (n: unknown) => unknown) {
  await act(async () => {
    render(<Host push={push} />);
  });
  await act(async () => { await Promise.resolve(); });
}

beforeEach(() => {
  resetLossLimitNoticesForTests();
  share.leader = true;
  share.snap = null;
  share.published = [];
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('useLossLimitNotices', () => {
  it('the reading window shows the trip, says it once and shares the answer', async () => {
    api.fetchLossLimit.mockResolvedValue(tripped());
    const push = vi.fn();
    await mount(push);
    expect(push).toHaveBeenCalledTimes(1);
    expect(push.mock.calls[0][0]).toMatchObject({ tone: 'bad', title: 'Daily loss limit reached' });
    expect(voice.speakDesk).toHaveBeenCalledWith('Daily loss limit reached on Paper.');
    expect(share.published).toHaveLength(1);
  });

  it('a following window shows the shared trip and never speaks or reads itself', async () => {
    share.leader = false;
    share.snap = { ts: Date.now(), payload: { schema_version: 1, view: tripped() } };
    const push = vi.fn();
    await mount(push);
    expect(api.fetchLossLimit).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledTimes(1);
    expect(voice.speakDesk).not.toHaveBeenCalled();
  });
});
