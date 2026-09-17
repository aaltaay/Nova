/**
 * Orders Today fill-latency cell -- format, tooltip, detective tone.
 * Face total and colors come from the API fill_audit object. Never invent ms.
 */
import type { FillAuditLevel, OrderFillAudit } from './types';

export const FILL_LATENCY_EM_DASH = '—';

function asInt(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Math.round(value);
}

/** Click-to-fill when filled, else click-to-terminal. */
export function fillLatencyFaceMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  if (!audit) return null;
  const fill = asInt(audit.place_to_fill_ms);
  if (fill != null) return fill;
  return asInt(audit.place_to_terminal_ms);
}

export function formatFillLatencyMs(ms: number | null | undefined): string {
  const n = asInt(ms);
  if (n == null || n < 0) return FILL_LATENCY_EM_DASH;
  if (n < 1000) return `${n}ms`;
  if (n % 1000 === 0) return `${n / 1000}s`;
  return `${(n / 1000).toFixed(1)}s`;
}

export function submitToFillMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  const fill = asInt(audit?.place_to_fill_ms);
  const submit = asInt(audit?.place_to_submit_ms);
  if (fill == null || submit == null) return null;
  const delta = fill - submit;
  return delta >= 0 ? delta : null;
}

/** warn/danger only when a real face total exists. ok stays default ink. */
export function fillLatencyTone(
  audit: OrderFillAudit | null | undefined,
): FillAuditLevel | null {
  if (fillLatencyFaceMs(audit) == null) return null;
  const level = audit?.level;
  if (level === 'warn' || level === 'danger') return level;
  if (level === 'ok') return 'ok';
  return null;
}

export function fillLatencyTooltip(
  audit: OrderFillAudit | null | undefined,
): string | undefined {
  if (fillLatencyFaceMs(audit) == null) return undefined;
  const lines = [
    `Nova → IBKR submit: ${formatFillLatencyMs(asInt(audit?.place_to_submit_ms))}`,
    `IBKR submit → fill: ${formatFillLatencyMs(submitToFillMs(audit))}`,
  ];
  if (asInt(audit?.place_to_fill_ms) != null) {
    lines.push(`Click → fill: ${formatFillLatencyMs(asInt(audit?.place_to_fill_ms))}`);
  } else {
    lines.push(
      `Click → terminal: ${formatFillLatencyMs(asInt(audit?.place_to_terminal_ms))}`,
    );
  }
  return lines.join(' -- ');
}
