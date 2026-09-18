/**
 * Orders Today fill-latency cell -- format, tooltip, detective tone.
 * Face total and colors come from the API fill_audit object. Never invent ms.
 */
import type { FillAuditLevel, OrderFillAudit } from './types';

export const FILL_LATENCY_EM_DASH = '—';
export const FILL_AUDIT_REASON_CLOCK_SKEW = 'clock_skew';

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

/**
 * Whole-second IBKR stamps vs Nova ms (IMCC BUY 106411: -296ms).
 * Any negative face total is clock skew -- never a fill before Place.
 */
export function isClockSkewFill(
  audit: OrderFillAudit | null | undefined,
): boolean {
  if (!audit) return false;
  if (audit.reason === FILL_AUDIT_REASON_CLOCK_SKEW) return true;
  const fill = asInt(audit.place_to_fill_ms);
  if (fill != null) return fill < 0;
  const terminal = asInt(audit.place_to_terminal_ms);
  return terminal != null && terminal < 0;
}

function clockSkewAbsMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  const fill = asInt(audit?.place_to_fill_ms);
  if (fill != null && fill < 0) return Math.abs(fill);
  const terminal = asInt(audit?.place_to_terminal_ms);
  if (terminal != null && terminal < 0) return Math.abs(terminal);
  const submit = asInt(audit?.place_to_submit_ms);
  if (submit != null && submit < 0) return Math.abs(submit);
  return null;
}

/** Click-to-fill when filled, else click-to-terminal. Invalid / skew stay blank. */
export function fillLatencyFaceMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  if (!audit || isInvalidFillClock(audit) || isClockSkewFill(audit)) return null;
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
  if (isClockSkewFill(audit)) return 'ok';
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
  if (isClockSkewFill(audit)) {
    const skew = clockSkewAbsMs(audit);
    const lines = [
      skew != null
        ? `Clocks disagree by ${skew}ms -- not a real negative fill`
        : 'Clocks disagree -- not a real negative fill',
    ];
    const submit = asInt(audit.place_to_submit_ms);
    if (submit != null) {
      lines.push(`Nova → submit (raw): ${submit}ms`);
    }
    return lines.join('\n');
  }
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
