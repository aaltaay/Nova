/**
 * What a proposal means for the operator's own Stage (ADR 042 draft, spec H), pure: Nova itself will take it
 * (`taken_by`), or it is not a trade (`not_a_trade`) -- both still raised, so they show, and both lock Stage
 * with the reason -- and the size Stage fills: the venue sleeve's risk per trade over the proposal's risk a
 * share, never Settings > Trade's default quantity. The board's frames are read raw, so every field is
 * checked here, never trusted.
 */
import {
  PROPOSAL_NOT_A_TRADE_NOVA,
  PROPOSAL_TAKEN_LINE,
  PROPOSAL_TAKEN_LOCK,
  SETUPS_STAGE_NO_ENTRY_WHY,
  SETUPS_STAGE_NO_STOP_WHY,
} from '../constantGroups/setups';
import { fmtPx } from './setupsFormat';
import type { SetupProposal } from './types';

export type TakenBy = 'bot' | 'auto_entry';

/** Who in Nova takes the proposal; null when nobody does (or the API is older). */
export function proposalTakenBy(p: SetupProposal): TakenBy | null {
  const t: unknown = p.taken_by;
  return t === 'bot' || t === 'auto_entry' ? t : null;
}

/** The reasons it is not a trade (an empty list when the API gives none); null when it is one. */
export function proposalNotATrade(p: SetupProposal): string[] | null {
  const n: unknown = p.not_a_trade;
  if (!n || typeof n !== 'object' || Array.isArray(n)) return null;
  const reasons = (n as { reasons?: unknown }).reasons;
  return Array.isArray(reasons) ? reasons.filter((r): r is string => typeof r === 'string' && r.trim() !== '') : [];
}

/** "Not a trade: grade C; the tape said wait." */
export function notATradeText(reasons: readonly string[]): string {
  return reasons.length ? `Not a trade: ${reasons.join('; ')}.` : 'Not a trade.';
}

/** The line the card says about Nova and this proposal; null when there is nothing to say. */
export function proposalVerdictLine(p: SetupProposal): { text: string; tone: 'nova' | 'notrade' } | null {
  const taken = proposalTakenBy(p);
  if (taken) return { text: PROPOSAL_TAKEN_LINE[taken], tone: 'nova' };
  const no = proposalNotATrade(p);
  return no ? { text: `${notATradeText(no)} ${PROPOSAL_NOT_A_TRADE_NOVA}`, tone: 'notrade' } : null;
}

/** The limit Stage fills: the planned entry, in the desk's decimals (4 under $1); empty without one. */
export function stageLimit(entry: number | null | undefined): string {
  return entry != null && Number.isFinite(entry) && entry > 0 ? fmtPx(entry) : '';
}

/** The proposal's risk a share: its own, else the distance from the entry to the stop (under it on a long,
 * over it on a short, ADR 049); null when neither is known and positive. */
export function proposalRisk(p: Pick<SetupProposal, 'risk' | 'entry' | 'stop'> & { side?: string | null }): number | null {
  if (p.risk != null && Number.isFinite(p.risk) && p.risk > 0) return p.risk;
  if (p.entry == null || p.stop == null) return null;
  const risk = p.side === 'short' ? p.stop - p.entry : p.entry - p.stop;
  return risk > 0 ? risk : null;
}

export interface StageSize {
  /** Whole shares; null when the risk per trade buys none (or nothing sizes it). */
  qty: number | null;
  /** Where the size comes from, said in the Stage button's hover. */
  text: string;
}

const usd = (v: number) => `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;

/** A risk a share in words: cents under a dollar. */
function perShare(risk: number): string {
  return risk < 1 ? `${Math.round(risk * 100)}¢` : usd(risk);
}

/** The risk per trade over the risk a share, in whole shares, with the words that say so. `source` names
 * where the risk per trade comes from ("the Paper sleeve's"). */
export function proposalStageSize(
  p: Pick<SetupProposal, 'risk' | 'entry' | 'stop'> & { side?: string | null },
  riskUsd: number,
  source: string,
): StageSize {
  const risk = proposalRisk(p);
  // A short needs its stop itself, not only a risk (no stop, no short).
  if (risk === null || (p.side === 'short' && p.stop == null)) return { qty: null, text: SETUPS_STAGE_NO_STOP_WHY };
  const n = riskUsd > 0 ? Math.floor(riskUsd / risk + 1e-9) : 0;
  if (n < 1) {
    const verb = p.side === 'short' ? 'shorts' : 'buys';
    return { qty: null, text: `${usd(riskUsd)} of risk (${source}) ${verb} no whole share at ${perShare(risk)} a share.` };
  }
  return {
    qty: n,
    text: `${n.toLocaleString('en-US')} shares: ${usd(riskUsd)} of risk (${source}) over ${perShare(risk)} a share`,
  };
}

/** Why Stage cannot fill the ticket for this proposal; null when it can. Nova taking it comes first. */
export function proposalStageLock(p: SetupProposal, size: StageSize): string | null {
  const taken = proposalTakenBy(p);
  if (taken) return PROPOSAL_TAKEN_LOCK[taken];
  const no = proposalNotATrade(p);
  if (no) return notATradeText(no);
  if (!stageLimit(p.entry)) return SETUPS_STAGE_NO_ENTRY_WHY;
  if (size.qty === null) return size.text;
  return null;
}
