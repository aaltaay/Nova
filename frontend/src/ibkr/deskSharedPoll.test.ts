/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DESK_POLL_LEADER_KEY_PREFIX, DESK_POLL_ACCOUNT_SHARE } from '../constants';
import {
  _resetDeskPollShareForTests,
  claimDeskPollLeader,
  publishDeskPollSnap,
  readDeskPollSnap,
} from './deskSharedPoll';

describe('deskSharedPoll', () => {
  beforeEach(() => {
    _resetDeskPollShareForTests();
  });

  afterEach(() => {
    _resetDeskPollShareForTests();
  });

  it('this tab claims when no leader exists', () => {
    expect(claimDeskPollLeader(DESK_POLL_ACCOUNT_SHARE, 1_800)).toBe(true);
    expect(claimDeskPollLeader(DESK_POLL_ACCOUNT_SHARE, 1_800)).toBe(true);
  });

  it('refuses claim while another owner heartbeat is fresh', () => {
    localStorage.setItem(
      `${DESK_POLL_LEADER_KEY_PREFIX}${DESK_POLL_ACCOUNT_SHARE}`,
      JSON.stringify({ owner: 'other-window', ts: Date.now() }),
    );
    expect(claimDeskPollLeader(DESK_POLL_ACCOUNT_SHARE, 1_800)).toBe(false);
  });

  it('takes over after the leader heartbeat goes stale', () => {
    localStorage.setItem(
      `${DESK_POLL_LEADER_KEY_PREFIX}${DESK_POLL_ACCOUNT_SHARE}`,
      JSON.stringify({ owner: 'other-window', ts: Date.now() - 5_000 }),
    );
    expect(claimDeskPollLeader(DESK_POLL_ACCOUNT_SHARE, 1_800)).toBe(true);
  });

  it('round-trips a snapshot', () => {
    publishDeskPollSnap(DESK_POLL_ACCOUNT_SHARE, { summary: { NetLiquidation: 9 } });
    const env = readDeskPollSnap<{ summary: { NetLiquidation: number } }>(
      DESK_POLL_ACCOUNT_SHARE,
    );
    expect(env?.payload.summary.NetLiquidation).toBe(9);
    expect(env?.ts).toBeGreaterThan(0);
  });
});
