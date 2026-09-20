/** @vitest-environment node */
import { describe, expect, it } from 'vitest';
import { buildTradingPrerequisites } from './tradingPrerequisites';
import { DESK_API_FAIL_STREAK_FOR_OVERLAY } from '../constants';

describe('recording cannot suppress trading prerequisites', () => {
  it('keeps the sustained API-down overlay visible while recording', () => {
    const state = buildTradingPrerequisites({
      health: { status: 'disconnected', latency_ms: 0, flag: 'API_DOWN' },
      ibkrConnected: false,
      apiFailStreak: DESK_API_FAIL_STREAK_FOR_OVERLAY,
      sessionRecording: true,
    });
    expect(state.autoOverlay).toBe(true);
  });
  it('keeps the wedged-loop overlay visible while recording', () => {
    const state = buildTradingPrerequisites({
      health: { status: 'connected', latency_ms: 0, ib_loop_lag_ms: { wedged: true } },
      ibkrConnected: true,
      sessionRecording: true,
    });
    expect(state.autoOverlay).toBe(true);
  });
});
