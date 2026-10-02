import { describe, expect, it } from 'vitest';
import {
  depthEmptyMessage,
  depthLiveBadge,
  depthLiveBadgeText,
} from './depthUiStatus';

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
