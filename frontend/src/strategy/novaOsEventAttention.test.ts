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
  it('maps a staged ticket to staged', () => {
    const r = receipt({ action: 'staged', payload: { event: 'staged' } });
    expect(mapNovaOsEventToAttention(r)).toEqual({ kind: 'staged', symbol: 'MOCK' });
  });

  it('maps executed_paper and executed_live to fill', () => {
    expect(
      mapNovaOsEventToAttention(receipt({ action: 'executed_paper', payload: { event: 'executed_paper' } })),
    ).toEqual({ kind: 'fill', symbol: 'MOCK' });
    expect(
      mapNovaOsEventToAttention(receipt({ action: 'executed_live', payload: { event: 'executed_live' } })),
    ).toEqual({ kind: 'fill', symbol: 'MOCK' });
  });

  it('maps a staged_expired decline to expired, but not other declines', () => {
    expect(
      mapNovaOsEventToAttention(
        receipt({ action: 'declined', payload: { event: 'staged_expired' } }),
      ),
    ).toEqual({ kind: 'expired', symbol: 'MOCK' });
    expect(
      mapNovaOsEventToAttention(
        receipt({ action: 'declined', payload: { event: 'placement_declined' } }),
      ),
    ).toBeNull();
  });

  it('maps bracket_closed / bracket_closed_unverified to stop', () => {
    expect(
      mapNovaOsEventToAttention(receipt({ payload: { event: 'bracket_closed' } })),
    ).toEqual({ kind: 'stop', symbol: 'MOCK' });
    expect(
      mapNovaOsEventToAttention(receipt({ payload: { event: 'bracket_closed_unverified' } })),
    ).toEqual({ kind: 'stop', symbol: 'MOCK' });
  });

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

  it('maps mode_change/force_signal to signal as mode_reset, but not raises', () => {
    expect(
      mapNovaOsEventToAttention(
        receipt({ kind: 'system', symbol: null, payload: { event: 'mode_change', to: 'signal' } }),
      ),
    ).toEqual({ kind: 'mode_reset', symbol: undefined });
    expect(
      mapNovaOsEventToAttention(
        receipt({ kind: 'system', symbol: null, payload: { event: 'force_signal', to: 'signal' } }),
      ),
    ).toEqual({ kind: 'mode_reset', symbol: undefined });
    expect(
      mapNovaOsEventToAttention(
        receipt({ kind: 'system', symbol: null, payload: { event: 'mode_change', to: 'confirm' } }),
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
