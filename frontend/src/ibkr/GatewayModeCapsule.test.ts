/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import { resolveCapsuleSelection } from './GatewayModeCapsule';

describe('resolveCapsuleSelection (ADR 020 venue pills)', () => {
  it('an explicit venue from status wins over every older field', () => {
    expect(resolveCapsuleSelection('live', 'live', 'live', 'live', 'paper')).toBe('paper');
    expect(resolveCapsuleSelection('paper', 'live', 'live', null, 'sim')).toBe('sim');
    expect(resolveCapsuleSelection('disconnected', 'live', null, null, 'live')).toBe('live');
  });

  it('keeps Live selected while a Live click is in flight even if the account is still paper', () => {
    expect(resolveCapsuleSelection('paper', 'paper', 'paper', 'live')).toBe('live');
  });

  it('mode is the venue: Paper on the live Gateway is Paper, whatever the port or IB account class says', () => {
    expect(resolveCapsuleSelection('paper', 'live', 'live')).toBe('paper');
    expect(resolveCapsuleSelection('live', 'live', 'paper')).toBe('live');
  });

  it('selects Sim when status.mode is sim even if Gateway is live', () => {
    expect(resolveCapsuleSelection('sim', 'live', 'live')).toBe('sim');
  });

  it('falls back to the IB account class, then the configured door, while disconnected', () => {
    expect(resolveCapsuleSelection('disconnected', 'live', 'paper')).toBe('paper');
    expect(resolveCapsuleSelection('disconnected', 'paper')).toBe('paper');
    expect(resolveCapsuleSelection('paper')).toBe('paper');
    expect(resolveCapsuleSelection('disconnected')).toBeNull();
  });
});
