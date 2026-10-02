/**
 * Orders Today fill-latency cell -- format, tooltip, detective tone.
 * Face total and colors come from the API fill_audit object. Never invent ms.
 * The face is click-to-fill only; an unfilled order's rest time is hover-only.
 */
import type { FillAuditLevel, OrderFillAudit } from './types';

export const FILL_LATENCY_EM_DASH = '—';
export const FILL_AUDIT_REASON_CLOCK_SKEW = 'clock_skew';
export const FILL_LATENCY_UNAVAILABLE = 'unavailable';

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

function formatHoverStep(
  ms: number | null | undefined,
  allowNegative = false,
): string {
  const n = asInt(ms);
  if (n == null) return FILL_LATENCY_UNAVAILABLE;
  if (n < 0 && !allowNegative) return FILL_LATENCY_UNAVAILABLE;
  return `${n}ms`;
}

function hasHoverStory(audit: OrderFillAudit): boolean {
  return (
    isClockSkewFill(audit) ||
    isInvalidFillClock(audit) ||
    asInt(audit.place_to_submit_ms) != null ||
    asInt(audit.place_to_fill_ms) != null ||
    asInt(audit.place_to_terminal_ms) != null
  );
}

function hoverSubmitToFill(audit: OrderFillAudit): string {
  if (isClockSkewFill(audit) || isInvalidFillClock(audit)) {
    return FILL_LATENCY_UNAVAILABLE;
  }
  const fill = asInt(audit.place_to_fill_ms);
  const submit = asInt(audit.place_to_submit_ms);
  if (fill == null || fill < 0 || submit == null) return FILL_LATENCY_UNAVAILABLE;
  return formatHoverStep(fill - submit);
}

/**
 * Click-to-fill, and only for a fill. Invalid / skew stay blank.
 *
 * An order that never filled has no face: click-to-terminal is how long it
 * rested before it was cancelled or expired, not latency (TNMG 2026-10-02: a
 * bot entry cancelled after its 3 s TTL read "3289ms"). The hover says it.
 * A backend from before this still sends that rest time as ``face_ms``, so a
 * row without a fill is blank whatever ``face_ms`` says.
 */
export function fillLatencyFaceMs(
  audit: OrderFillAudit | null | undefined,
): number | null {
  if (!audit || isInvalidFillClock(audit) || isClockSkewFill(audit)) return null;
  const fill = asInt(audit.place_to_fill_ms);
  if (fill == null) return null;
  if (audit.face_ms !== undefined) {
    const face = asInt(audit.face_ms);
    return face != null && face > 0 ? face : null;
  }
  return fill > 0 ? fill : null;
}

export function formatFillLatencyMs(ms: number | null | undefined): string {
  const n = asInt(ms);
  if (n == null || n === 0) return FILL_LATENCY_EM_DASH;
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
  if (!audit || !hasHoverStory(audit)) return undefined;
  const invalid = isInvalidFillClock(audit);
  const skew = isClockSkewFill(audit);
  const lines: string[] = [];
  if (skew) {
    const absMs = clockSkewAbsMs(audit);
    lines.push(
      absMs != null
        ? `Clocks disagree by ${absMs}ms -- not a real negative fill`
        : 'Clocks disagree -- not a real negative fill',
    );
  }
  const submit = asInt(audit.place_to_submit_ms);
  const submitLabel =
    skew && submit != null && submit < 0
      ? `${formatHoverStep(submit, true)} (raw)`
      : formatHoverStep(submit, true);
  lines.push(`Nova → submit: ${submitLabel}`);
  const fill = asInt(audit.place_to_fill_ms);
  const terminal = asInt(audit.place_to_terminal_ms);
  if (!skew && !invalid && fill == null && terminal != null && terminal >= 0) {
    lines.push(
      `Not filled: it rested ${formatHoverStep(terminal)}, then closed -- not latency`,
    );
    return lines.join('\n');
  }
  lines.push(`Submit → fill: ${hoverSubmitToFill(audit)}`);
  if (!skew && !invalid && fill != null && fill >= 0) {
    lines.push(`Click → fill: ${formatHoverStep(fill)}`);
  } else {
    lines.push(`Click → fill: ${FILL_LATENCY_UNAVAILABLE}`);
  }
  if (invalid) {
    lines.push(`Clock: invalid (${audit.reason})`);
  }
  return lines.join('\n');
}
