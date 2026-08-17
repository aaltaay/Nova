/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import { resolveCapsuleSelection } from './GatewayModeCapsule';

describe('resolveCapsuleSelection', () => {
  it('shows the configured Gateway target, not a stale paper session', () => {
    expect(resolveCapsuleSelection('paper', 'live')).toBe('live');
    expect(resolveCapsuleSelection('disconnected', 'live')).toBe('live');
  });

  it('shows paper when that is the configured target', () => {
    expect(resolveCapsuleSelection('live', 'paper')).toBe('paper');
    expect(resolveCapsuleSelection('disconnected', 'paper')).toBe('paper');
  });

  it('falls back to session mode when gateway_mode is unknown', () => {
    expect(resolveCapsuleSelection('paper')).toBe('paper');
    expect(resolveCapsuleSelection('live')).toBe('live');
    expect(resolveCapsuleSelection('disconnected')).toBeNull();
  });
});
