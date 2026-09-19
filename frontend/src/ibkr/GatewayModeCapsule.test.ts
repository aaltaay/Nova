/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import { resolveCapsuleSelection } from './GatewayModeCapsule';

describe('resolveCapsuleSelection', () => {
  it('keeps Live selected while a Live click is in flight even if the account is still paper', () => {
    expect(resolveCapsuleSelection('paper', 'paper', 'paper', 'live')).toBe('live');
  });

  it('shows the IB account class, not the port label, once idle', () => {
    expect(resolveCapsuleSelection('live', 'live', 'paper')).toBe('paper');
    expect(resolveCapsuleSelection('paper', 'paper', 'live')).toBe('live');
  });

  it('selects Sim when status.mode is sim even if Gateway is live', () => {
    expect(resolveCapsuleSelection('sim', 'live', 'live')).toBe('sim');
  });

  it('falls back to configured door then session mode', () => {
    expect(resolveCapsuleSelection('paper', 'live')).toBe('live');
    expect(resolveCapsuleSelection('disconnected', 'paper')).toBe('paper');
    expect(resolveCapsuleSelection('paper')).toBe('paper');
    expect(resolveCapsuleSelection('disconnected')).toBeNull();
  });
});
