/**
 * The tape flow score in words (ADR 034): one number from -1 (sellers) to +1
 * (buyers), its label, and each of the four readings it averages. A reading
 * Nova could not take is said as unknown, never as 0.
 */
import { TAPE_FLOW_LABEL_WORDS, TAPE_FLOW_READING_WORDS } from '../constantGroups/setups';
import type { TapeFlow } from './types';

function signed(v: number): string {
  return `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}`;
}

/** The flow score's line in the tape tip: the score, its label, and each reading. */
export function flowLine(flow: TapeFlow | null | undefined): string {
  if (!flow) return '';
  const said = TAPE_FLOW_LABEL_WORDS[flow.label] ?? flow.label;
  const head = flow.score == null ? `Flow: ${said}` : `Flow ${signed(flow.score)}: ${said}`;
  const parts = TAPE_FLOW_READING_WORDS.map(([key, words]) => {
    const v = flow.readings?.[key];
    return v == null ? `${words} unknown` : `${words} ${signed(v)}`;
  });
  return `${head} (${parts.join(' · ')}).`;
}
