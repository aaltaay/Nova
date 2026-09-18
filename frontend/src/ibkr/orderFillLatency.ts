/**
 * Orders Today fill-latency cell -- format, tooltip, detective tone.
 * Face total and colors come from the API fill_audit object. Never invent ms.
 */
import type { FillAuditLevel, OrderFillAudit } from './types';

export const FILL_LATENCY_EM_DASH = '—';

const INVALID_CLOCK_REASONS = new Set([
  'timezone_shaped_clock',
  'impossible_fill_clock',
]);

function asInt(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Math.round(value);
}

export function isInvalidFillClock(
  audit: OrderFillAudit | null | undefined,
): boolean {
  const reason = audit?.reason;
  return typeof reason === 'string' && INVALID_CLOCK_REASONS.has(reason);
}

/** Click-to-fill when filled, else click-to-terminal. Invalid clocks stay blank. */
export function fillLatencyFaceMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  if (!audit || isInvalidFillClock(audit)) return null;
  const fill = asInt(audit.place_to_fill_ms);
  if (fill != null) return fill;
  return asInt(audit.place_to_terminal_ms);
}

export function formatFillLatencyMs(ms: number | null | undefined): string {
  const n = asInt(ms);
  if (n == null) return FILL_LATENCY_EM_DASH;
  return `${n}ms`;
}

export function submitToFillMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  const fill = asInt(audit?.place_to_fill_ms);
  const submit = asInt(audit?.place_to_submit_ms);
  if (fill == null || submit == null) return null;
  return fill - submit;
}

/** warn/danger only when a real face total exists. ok stays default ink. */
export function fillLatencyTone(
  audit: OrderFillAudit | null | undefined,
): FillAuditLevel | null {
  if (isInvalidFillClock(audit)) {
    const level = audit?.level;
    if (level === 'warn' || level === 'danger') return level;
    return 'warn';
  }
  if (fillLatencyFaceMs(audit) == null) return null;
  const level = audit?.level;
  if (level === 'warn' || level === 'danger') return level;
  if (level === 'ok') return 'ok';
  return null;
}

export function fillLatencyTooltip(
  audit: OrderFillAudit | null | undefined,
): string | undefined {
  if (!audit) return undefined;
  const face = fillLatencyFaceMs(audit);
  const invalid = isInvalidFillClock(audit);
  if (face == null && !invalid) return undefined;
  const lines = [
    `Nova → submit: ${formatFillLatencyMs(asInt(audit.place_to_submit_ms))}`,
    `Submit → fill: ${formatFillLatencyMs(submitToFillMs(audit))}`,
  ];
  if (asInt(audit.place_to_fill_ms) != null && !invalid) {
    lines.push(`Click → fill: ${formatFillLatencyMs(asInt(audit.place_to_fill_ms))}`);
  } else if (asInt(audit.place_to_terminal_ms) != null && !invalid) {
    lines.push(
      `Click → terminal: ${formatFillLatencyMs(asInt(audit.place_to_terminal_ms))}`,
    );
  } else {
    lines.push(`Click → fill: ${FILL_LATENCY_EM_DASH}`);
  }
  if (invalid) {
    lines.push(`Clock: invalid (${audit.reason})`);
  }
  return lines.join('\n');
}
