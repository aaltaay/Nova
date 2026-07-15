/**
 * Maps append-only Nova OS event receipts (GET /api/nova-os/events) to
 * attention-strip pushes, and a hook that polls the feed globally.
 *
 * This is the missing link the P3 attention framework never had: kinds like
 * `staged`/`expired`/`fill`/`stop`/`kill`/`archive_fail` existed in copy/type
 * unions but nothing ever pushed them — only decide() BUY/WAIT/NO_BUY verdicts
 * reached the strip (see DecisionPanel.tsx). Runs independent of which tab is
 * open so a kill switch or an expired approval is never silently missed.
 */
import { useEffect, useRef } from 'react';
import {
  API_BASE_URL,
  NOVA_OS_EVENT_ATTENTION_POLL_INTERVAL_MS,
  NOVA_OS_EVENT_ATTENTION_POLL_LIMIT,
} from '../constants';
import { pushNovaOsAttention } from './novaOsAttention';
import type { NovaOsAttentionKind } from './novaOsAttention';
import type { NovaOsReceipt } from './types';

const EVENTS_API = `${API_BASE_URL}/api/nova-os/events`;

export interface MappedAttention {
  kind: NovaOsAttentionKind;
  symbol?: string;
}

/** Pure — one event receipt in, at most one attention push out (or null to
 * skip). Kept separate from the hook so the mapping is unit-testable without
 * fetch/timers. */
export function mapNovaOsEventToAttention(event: NovaOsReceipt): MappedAttention | null {
  const symbol = event.symbol ?? undefined;
  const payloadEvent = event.payload?.['event'];

  if (event.kind === 'action') {
    if (event.action === 'staged') return { kind: 'staged', symbol };
    if (event.action === 'executed_paper' || event.action === 'executed_live') {
      return { kind: 'fill', symbol };
    }
    if (event.action === 'declined' && payloadEvent === 'staged_expired') {
      return { kind: 'expired', symbol };
    }
    if (payloadEvent === 'bracket_closed' || payloadEvent === 'bracket_closed_unverified') {
      return { kind: 'stop', symbol };
    }
    return null;
  }

  if (event.kind === 'system') {
    if (payloadEvent === 'kill_switch') return { kind: 'kill' };
    if (payloadEvent === 'risk_halt') return { kind: 'risk_halt' };
    if (payloadEvent === 'archive_upload_failed') return { kind: 'archive_fail' };
    if (
      (payloadEvent === 'mode_change' || payloadEvent === 'force_signal') &&
      event.payload?.['to'] === 'signal'
    ) {
      return { kind: 'mode_reset' };
    }
  }

  return null;
}

/** Poll /api/nova-os/events and push new receipts into the attention strip.
 * Mount once near the app root (not per-tab) — see StrategyPage. The first
 * poll only records a high-water mark; it never backfills history that
 * predates mount, so re-opening a tab can't replay old kill/expiry noise. */
export function useNovaOsEventAttention(enabled: boolean): void {
  const lastIdRef = useRef(0);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(`${EVENTS_API}?limit=${NOVA_OS_EVENT_ATTENTION_POLL_LIMIT}`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const rows: NovaOsReceipt[] = data.events ?? [];
        if (rows.length === 0) return;

        if (!initializedRef.current) {
          initializedRef.current = true;
          lastIdRef.current = Math.max(...rows.map((r) => r.id ?? 0));
          return;
        }

        const newRows = rows
          .filter((r) => (r.id ?? 0) > lastIdRef.current)
          .sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
        for (const row of newRows) {
          const mapped = mapNovaOsEventToAttention(row);
          if (mapped) pushNovaOsAttention(mapped.kind, { symbol: mapped.symbol });
        }
        lastIdRef.current = Math.max(lastIdRef.current, ...rows.map((r) => r.id ?? 0));
      } catch {
        // Best-effort notification layer — the events API itself, not this
        // poller, is the audit source of truth. Stay silent and retry.
      }
    }

    poll();
    const interval = setInterval(poll, NOVA_OS_EVENT_ATTENTION_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled]);
}
