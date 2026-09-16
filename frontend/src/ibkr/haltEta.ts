/** Pure LULD / halt chip clock -- mirrors backend/ibkr/halt_eta.py. */
import type { HaltSnapshot } from '../types/ticker';
import {
  HALT_KIND_LULD,
  HALT_KIND_REGULATORY,
  HALT_KIND_UNKNOWN,
  HALT_LABEL_REGULATORY,
  HALT_LABEL_STILL,
  HALT_LABEL_UNKNOWN,
  HALT_RULE_LULD,
  HALT_RULE_REGULATORY,
  HALT_RULE_UNKNOWN,
  HALT_START_OBSERVED_NOTE,
  HALT_TYPE_LULD,
  HALT_TYPE_REGULATORY,
  HALT_TYPE_UNKNOWN,
  LULD_CONFIDENT_WINDOW_SEC,
  LULD_PAUSE_SEC,
} from '../constantGroups/halt_eta';
import { STOCK_VIEW_CLOCK_TIMEZONE } from '../constantGroups/chart_api';

export type HaltChipView = {
  kind: string;
  phase: string;
  label: string;
  tooltip: string;
};

function minutesLeft(remainingSec: number): number {
  if (remainingSec <= 0) return 0;
  return Math.max(1, Math.ceil(remainingSec / 60));
}

export function luldPhase(elapsedSec: number): string {
  if (elapsedSec < LULD_PAUSE_SEC) return 'luld_pause';
  if (elapsedSec < LULD_CONFIDENT_WINDOW_SEC) return 'luld_extended';
  return 'luld_still';
}

export function luldLabel(elapsedSec: number): string {
  const phase = luldPhase(elapsedSec);
  if (phase === 'luld_pause') {
    return `LULD · ~${minutesLeft(LULD_PAUSE_SEC - elapsedSec)}m left`;
  }
  if (phase === 'luld_extended') {
    return `Extended · ~${minutesLeft(LULD_CONFIDENT_WINDOW_SEC - elapsedSec)}m`;
  }
  return HALT_LABEL_STILL;
}

function formatHaltStartEt(haltStart: number | null | undefined): string {
  if (haltStart == null || !Number.isFinite(haltStart)) {
    return `unknown (${HALT_START_OBSERVED_NOTE})`;
  }
  try {
    return `${new Date(haltStart * 1000).toLocaleString('en-US', {
      timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })} ET (${HALT_START_OBSERVED_NOTE})`;
  } catch {
    return `${haltStart} (${HALT_START_OBSERVED_NOTE})`;
  }
}

function tooltipFor(
  haltType: string,
  haltStart: number | null | undefined,
  rule: string,
  reason: string | null | undefined,
): string {
  const lines = [
    `Halt type: ${haltType}`,
    `Halt start: ${formatHaltStartEt(haltStart)}`,
    `Rule: ${rule}`,
  ];
  if (reason) lines.push(`Reason: ${reason}`);
  return lines.join('\n');
}

export function haltChipView(
  halt: HaltSnapshot | null | undefined,
  nowMs: number,
): HaltChipView | null {
  if (!halt?.halted || !halt.kind) return null;
  const nowSec = nowMs / 1000;
  const elapsed = halt.halt_start != null
    ? Math.max(0, nowSec - halt.halt_start)
    : 0;
  const reason = halt.reason ?? null;
  const ruleFromWire = halt.rule ?? null;

  if (halt.kind === HALT_KIND_LULD) {
    return {
      kind: HALT_KIND_LULD,
      phase: luldPhase(elapsed),
      label: luldLabel(elapsed),
      tooltip: tooltipFor(
        HALT_TYPE_LULD,
        halt.halt_start,
        ruleFromWire ?? HALT_RULE_LULD,
        reason,
      ),
    };
  }
  if (halt.kind === HALT_KIND_REGULATORY) {
    return {
      kind: HALT_KIND_REGULATORY,
      phase: HALT_KIND_REGULATORY,
      label: HALT_LABEL_REGULATORY,
      tooltip: tooltipFor(
        HALT_TYPE_REGULATORY,
        halt.halt_start,
        ruleFromWire ?? HALT_RULE_REGULATORY,
        reason,
      ),
    };
  }
  return {
    kind: HALT_KIND_UNKNOWN,
    phase: HALT_KIND_UNKNOWN,
    label: HALT_LABEL_UNKNOWN,
    tooltip: tooltipFor(
      HALT_TYPE_UNKNOWN,
      halt.halt_start,
      ruleFromWire ?? HALT_RULE_UNKNOWN,
      reason,
    ),
  };
}
