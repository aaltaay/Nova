/** Pure LULD / halt chip clock -- mirrors backend/ibkr/halt_eta.py. */
import type { HaltSnapshot } from '../types/ticker';
import {
  HALT_BADGE_LULD,
  HALT_BADGE_NEWS,
  HALT_BADGE_UNK,
  HALT_EXCHANGE_PENDING_NOTE,
  HALT_KIND_LULD,
  HALT_KIND_REGULATORY,
  HALT_KIND_UNKNOWN,
  HALT_LABEL_EXTENDED,
  HALT_LABEL_REGULATORY,
  HALT_LABEL_UNKNOWN,
  HALT_RULE_LULD,
  HALT_RULE_REGULATORY,
  HALT_RULE_UNKNOWN,
  HALT_START_LATE_NOTE,
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
  badge: string;
  phase: string;
  label: string;
  tooltip: string;
  startLate: boolean;
  exchangeStatus: string;
};

export function formatClock(elapsedSec: number): string {
  const total = Math.max(0, Math.floor(elapsedSec));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const rem = minutes % 60;
    return `${hours}:${String(rem).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function luldPhase(elapsedSec: number): string {
  if (elapsedSec < LULD_PAUSE_SEC) return 'luld_pause';
  if (elapsedSec < LULD_CONFIDENT_WINDOW_SEC) return 'luld_auction';
  return 'luld_extended';
}

export function luldLabel(
  elapsedSec: number,
  startLate = false,
  hasOfficialStart = false,
): string {
  const clock = formatClock(elapsedSec);
  const confident = !startLate || hasOfficialStart;
  if (!confident) return `${HALT_BADGE_LULD} · ${clock}`;
  const phase = luldPhase(elapsedSec);
  if (phase === 'luld_pause') {
    return `${HALT_BADGE_LULD} · ${clock} · ${formatClock(LULD_PAUSE_SEC - elapsedSec)} left`;
  }
  if (phase === 'luld_auction') {
    return `Auction · ${clock} · ${formatClock(LULD_CONFIDENT_WINDOW_SEC - elapsedSec)} left`;
  }
  return HALT_LABEL_EXTENDED;
}

function formatHaltStartEt(haltStart: number | null | undefined, note: string): string {
  if (haltStart == null || !Number.isFinite(haltStart)) {
    return `unknown (${note})`;
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
    })} ET (${note})`;
  } catch {
    return `${haltStart} (${note})`;
  }
}

function formatResumeEt(ts: number | null | undefined): string | null {
  if (ts == null || !Number.isFinite(ts)) return null;
  try {
    return `${new Date(ts * 1000).toLocaleString('en-US', {
      timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })} ET`;
  } catch {
    return null;
  }
}

function tooltipFor(halt: HaltSnapshot, haltType: string, rule: string): string {
  const lines = [
    `Halt type: ${haltType}`,
    `Halt start: ${formatHaltStartEt(halt.halt_start, HALT_START_OBSERVED_NOTE)}`,
    `Rule: ${rule}`,
  ];
  if (halt.start_late) lines.push(`Honesty: ${HALT_START_LATE_NOTE}`);
  if (halt.reason) lines.push(`Reason: ${halt.reason}`);
  const ex = halt.exchange;
  if (!ex || !ex.matched) {
    lines.push(HALT_EXCHANGE_PENDING_NOTE);
    return lines.join('\n');
  }
  if (ex.reason_code) lines.push(`Nasdaq reason: ${ex.reason_code}`);
  if (ex.pause_threshold) lines.push(`Pause threshold: ${ex.pause_threshold}`);
  if (ex.official_halt_start != null) {
    lines.push(`Nasdaq halt start: ${formatHaltStartEt(ex.official_halt_start, 'Nasdaq Trade Halt RSS')}`);
  }
  const quote = formatResumeEt(ex.quote_resume);
  const trade = formatResumeEt(ex.trade_resume);
  if (quote) lines.push(`Nasdaq quote resume: ${quote}`);
  if (trade) lines.push(`Nasdaq trade resume: ${trade}`);
  if (!quote && !trade) {
    lines.push('Nasdaq scheduled resume: none listed (not invented)');
  }
  return lines.join('\n');
}

export function haltChipView(
  halt: HaltSnapshot | null | undefined,
  nowMs: number,
): HaltChipView | null {
  if (!halt?.halted || !halt.kind) return null;
  const nowSec = nowMs / 1000;
  const official = halt.exchange?.official_halt_start ?? null;
  const hasOfficial = official != null && Number.isFinite(official);
  const clockStart = hasOfficial ? official : halt.halt_start;
  const elapsed = clockStart != null ? Math.max(0, nowSec - clockStart) : 0;
  const startLate = Boolean(halt.start_late);
  const exchangeStatus = halt.exchange?.status ?? 'pending';
  const reason = halt.reason ?? null;
  const ruleFromWire = halt.rule ?? null;

  if (halt.kind === HALT_KIND_LULD) {
    return {
      kind: HALT_KIND_LULD,
      badge: HALT_BADGE_LULD,
      phase: luldPhase(elapsed),
      label: luldLabel(elapsed, startLate, hasOfficial),
      startLate,
      exchangeStatus,
      tooltip: tooltipFor(halt, HALT_TYPE_LULD, ruleFromWire ?? HALT_RULE_LULD),
    };
  }
  if (halt.kind === HALT_KIND_REGULATORY) {
    return {
      kind: HALT_KIND_REGULATORY,
      badge: HALT_BADGE_NEWS,
      phase: HALT_KIND_REGULATORY,
      label: HALT_LABEL_REGULATORY,
      startLate,
      exchangeStatus,
      tooltip: tooltipFor(
        { ...halt, reason },
        HALT_TYPE_REGULATORY,
        ruleFromWire ?? HALT_RULE_REGULATORY,
      ),
    };
  }
  return {
    kind: HALT_KIND_UNKNOWN,
    badge: HALT_BADGE_UNK,
    phase: HALT_KIND_UNKNOWN,
    label: HALT_LABEL_UNKNOWN,
    startLate,
    exchangeStatus,
    tooltip: tooltipFor(halt, HALT_TYPE_UNKNOWN, ruleFromWire ?? HALT_RULE_UNKNOWN),
  };
}
