import { describe, expect, it } from 'vitest';
import {
  depthEmptyMessage,
  depthLentText,
  depthLiveBadge,
  depthLiveBadgeText,
} from './depthUiStatus';

describe('depthLentText (ADR 043 decision 6)', () => {
  it("names the setup that took the line and why, and when it comes back", () => {
    expect(depthLentText({ symbol: 'AISP', setupType: 'first_pullback', tier: 'near', why: 'near its trigger' })).toBe(
      "Level 2 lent to AISP's first pullback (near its trigger) — back when it ends or when you bring this tab to the front",
    );
  });

  it("says a trade and the other setups in the desk's words", () => {
    expect(depthLentText({ symbol: 'IPDN', setupType: 'flat_top_breakout', tier: 'trade', why: null })).toBe(
      "Level 2 lent to IPDN's flat-top breakout (in a trade) — back when it ends or when you bring this tab to the front",
    );
  });

  it("takes the backend's words for a reason the desk does not know", () => {
    expect(depthLentText({ symbol: 'AISP', setupType: 'some_new_setup', tier: null, why: 'waiting' })).toContain(
      "AISP's some new setup (waiting)",
    );
  });

  it('a frame that names no borrower still says the line is lent and when it comes back', () => {
    expect(depthLentText({ symbol: null, setupType: null, tier: null, why: null })).toBe(
      "Level 2 lent to one of Nova's setups — back when it ends or when you bring this tab to the front",
    );
  });
});

describe('depthEmptyMessage', () => {
  it('surfaces backend errors instead of Connecting…', () => {
    expect(
      depthEmptyMessage('SHPH', false, 'Symbol cap reached (3 max simultaneous depth streams)'),
    ).toContain('Symbol cap reached');
  });

  it('says Waiting when connected with no book yet', () => {
    expect(depthEmptyMessage('SHPH', true, null)).toBe('Waiting for book data…');
  });

  it('says Connecting when the socket is not up yet', () => {
    expect(depthEmptyMessage('SHPH', false, null)).toBe('Connecting depth for SHPH…');
  });
});

describe('depthLiveBadge', () => {
  it('prefers Symbol-cap error over Reconnecting when a prior book is shown', () => {
    const badge = depthLiveBadge(
      false,
      'Symbol cap reached (3 max simultaneous depth streams)',
      false,
    );
    expect(badge).toEqual({
      kind: 'error',
      text: 'Symbol cap reached (3 max simultaneous depth streams)',
    });
    expect(depthLiveBadgeText(badge)).toContain('Symbol cap reached');
  });

  it('shows Reconnecting only when disconnected with no error', () => {
    expect(depthLiveBadgeText(depthLiveBadge(false, null, false))).toBe(
      'Reconnecting depth…',
    );
  });

  it('shows L1 fallback when connected on entitlement fallback', () => {
    expect(depthLiveBadgeText(depthLiveBadge(true, null, true))).toContain('Level 1 only');
  });

  it('shows no badge when connected with full depth', () => {
    expect(depthLiveBadge(true, null, false)).toBeNull();
  });
});
