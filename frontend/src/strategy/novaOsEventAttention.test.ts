/** Vitest: pure event-receipt → attention-kind mapping (no fetch/timers). */
import { describe, expect, it } from 'vitest';
import { mapNovaOsEventToAttention } from './novaOsEventAttention';
import type { NovaOsReceipt } from './types';

function receipt(overrides: Partial<NovaOsReceipt>): NovaOsReceipt {
  return {
    id: 1,
    policy_version: 'v1',
    kind: 'action',
    symbol: 'MOCK',
    decision: null,
    action: null,
    mode: 'signal',
    reason_codes: [],
    would_execute: false,
    executed: false,
    payload: {},
    ...overrides,
  };
}

describe('mapNovaOsEventToAttention', () => {
  it('maps system events to kill / risk_halt / archive_fail', () => {
    expect(
      mapNovaOsEventToAttention(receipt({ kind: 'system', symbol: null, payload: { event: 'kill_switch' } })),
    ).toEqual({ kind: 'kill', symbol: undefined });
    expect(
      mapNovaOsEventToAttention(receipt({ kind: 'system', symbol: null, payload: { event: 'risk_halt' } })),
    ).toEqual({ kind: 'risk_halt', symbol: undefined });
    expect(
      mapNovaOsEventToAttention(
        receipt({ kind: 'system', symbol: null, payload: { event: 'archive_upload_failed' } }),
      ),
    ).toEqual({ kind: 'archive_fail', symbol: undefined });
  });

  it('ignores the retired executor receipts (staged, fills, mode resets)', () => {
    expect(mapNovaOsEventToAttention(receipt({ action: 'staged' }))).toBeNull();
    expect(mapNovaOsEventToAttention(receipt({ action: 'executed_paper' }))).toBeNull();
    expect(
      mapNovaOsEventToAttention(
        receipt({ kind: 'system', symbol: null, payload: { event: 'force_signal', to: 'signal' } }),
      ),
    ).toBeNull();
  });

  it('ignores unmapped action/system events and decision receipts', () => {
    expect(
      mapNovaOsEventToAttention(receipt({ action: 'confirmed', payload: { event: 'staged_approved' } })),
    ).toBeNull();
    expect(mapNovaOsEventToAttention(receipt({ kind: 'decision', payload: {} }))).toBeNull();
  });
});
