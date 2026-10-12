/**
 * The target menu on the wire (#845, operator decisions 2026-10-09 and 2026-10-12; backend
 * `setup_scanner/targets.py`): exits follow the levels the operator's material sells at, in two parts. Every setup
 * row, plan, proposal and held block carries target 1 (`target1`; a plan's `target`), and beside it `target2` (null:
 * everything sells at target 1), `target1_fraction` (the share sold at target 1: 0.5 with a target 2, 1.0 without)
 * and `targets` -- each target's kind, price and the few words it came from ("+20c", "1c under $5.50", "1c under
 * HOD 6.12"). No target is a multiple of the risk: R is the unit a result is measured in (1R = the risk a share),
 * never where a trade sells. The Trader's plan and held card and the board's hovers read the same words here. Pure.
 */
import { fmtPx } from './setupsFormat';

/** One part's target: what it came from (`fixed`, `round`, `next_level`, `pullback_high`, `hod`), its price, why. */
export interface TargetLeg {
  kind: string;
  price: number;
  why: string;
}

/** The stop a template picked from the menu: the pattern's own, or a few cents past a half / whole dollar. */
export interface TargetStop {
  kind: 'pattern' | 'round' | string;
  why: string;
  round: number | null;
}

/** The strategy's choice from the menu: a kind for each part, the fixed amount, target 1's share and the stop. */
export interface TargetRule {
  first: string;
  second: string;
  fixed: number | null;
  split: number | null;
  stop: string;
}

export interface SetupTargets {
  first: TargetLeg;
  second: TargetLeg | null;
  hod: number | null;
  pullback_high: number | null;
  stop: TargetStop | null;
  rule: TargetRule | null;
}

/** What a level set carries beside target 1; each is absent from a backend before the menu. */
export interface TargetFields {
  target2?: number | null;
  target1_fraction?: number | null;
  targets?: SetupTargets | null;
}

type Obj = Record<string, unknown>;

function obj(v: unknown): Obj | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' ? v : null;
}

function leg(raw: unknown): TargetLeg | null {
  const l = obj(raw);
  const price = num(l?.price);
  if (!l || price === null) return null;
  return { kind: str(l.kind) ?? '', price, why: str(l.why) ?? '' };
}

/** `targets` off the wire; null without a target 1 (an older backend, or a plan with no stop yet). */
export function normalizeTargets(raw: unknown): SetupTargets | null {
  const t = obj(raw);
  const first = leg(t?.first);
  if (!t || !first) return null;
  const stop = obj(t.stop);
  const rule = obj(t.rule);
  return {
    first,
    second: leg(t.second),
    hod: num(t.hod),
    pullback_high: num(t.pullback_high),
    stop: stop && typeof stop.why === 'string' ? { kind: str(stop.kind) ?? 'pattern', why: stop.why, round: num(stop.round) } : null,
    rule: rule ? {
      first: str(rule.first) ?? '', second: str(rule.second) ?? '', fixed: num(rule.fixed), split: num(rule.split),
      stop: str(rule.stop) ?? '',
    } : null,
  };
}

/** A level set's target fields: an older backend's read as one target (no target 2, everything at target 1). A
 *  share the wire does not state with a target 2 is null -- never guessed. */
export function normalizeTargetFields(raw: unknown): Required<TargetFields> {
  const o = obj(raw);
  const target2 = num(o?.target2);
  const f = num(o?.target1_fraction);
  const fraction = f !== null && f > 0 && f <= 1 ? f : null;
  return {
    target2,
    target1_fraction: target2 === null ? 1 : fraction,
    targets: normalizeTargets(o?.targets),
  };
}

/** "50%": the share of the shares a target sells; null without a target 2 or a stated split. */
export function targetShare(fraction: number | null | undefined, which: 1 | 2): string | null {
  if (fraction == null || !(fraction > 0) || fraction >= 1) return null;
  return `${Math.round((which === 1 ? fraction : 1 - fraction) * 100)}%`;
}

/** "half sells there" / "30% sells there" (a short's "is covered"). */
function shareWords(fraction: number | null | undefined, short: boolean): string {
  const verb = short ? 'is covered there' : 'sells there';
  if (fraction === 0.5) return `half ${verb}`;
  const pct = targetShare(fraction, 1);
  return pct ? `${pct} ${verb}` : `the first part ${verb}`;
}

/**
 * A setup's targets in one sentence for its hover (a short's covers): "Target 1 4.49 (1c under $4.50): half sells
 * there, the rest at target 2 4.99 (1c under $5.00). The stop stays where it is." Each why is the row's own, so the
 * sentence says the strategy's menu choice; a backend before the menu gives the price alone.
 */
export function targetSentence(s: { target1: number } & TargetFields, short = false): string {
  const name = short ? 'Cover' : 'Target';
  const why = (w: string | null | undefined) => (w ? ` (${w})` : '');
  const one = `${name} 1 ${fmtPx(s.target1)}${why(s.targets?.first.why)}`;
  if (s.target2 === undefined && !s.targets) return `${one}.`;
  const stays = short ? 'The buy stop stays where it is.' : 'The stop stays where it is.';
  if (s.target2 == null) return `${one}: everything ${short ? 'is covered' : 'sells'} there. ${stays}`;
  return `${one}: ${shareWords(s.target1_fraction, short)}, the rest at ${name.toLowerCase()} 2 ${fmtPx(s.target2)}`
    + `${why(s.targets?.second?.why)}. ${stays}`;
}
