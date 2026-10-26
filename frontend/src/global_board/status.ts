/**
 * The Global page's notes, on one line in its head (ADR 060 amendment: the page never scrolls, so a note never pushes
 * the board down): a failed poll, IBKR's own error, another period still loading, the first reads, and what the
 * reads wait for -- with IBKR's history requests left against the number Global reads above.
 */
import { GLOBAL_LOADING, GLOBAL_WAITING_HISTORY_FIRST, GLOBAL_WAITING_LINES, PERIOD_LABEL } from './constants';
import type { Budget, GlobalBoard, Period } from './types';

export interface Note {
  id: 'error' | 'ibkr' | 'period' | 'loading' | 'waiting';
  text: string;
  warn?: boolean;
}

export function waitingWords(budget: Budget): string | null {
  if (budget.waiting === 'lines') return GLOBAL_WAITING_LINES;
  if (budget.waiting !== 'history') return null;
  const left = budget.history_left;
  return left == null
    ? `Waiting its turn for IBKR history (${GLOBAL_WAITING_HISTORY_FIRST}).`
    : `Waiting its turn for IBKR history: ${left} requests left this 10 minutes, Global reads above `
      + `${budget.history_headroom} (${GLOBAL_WAITING_HISTORY_FIRST}).`;
}

export function statusNotes(board: GlobalBoard, wanted: Period, error: string | null): Note[] {
  const out: Note[] = [];
  if (error) out.push({ id: 'error', text: `${error} -- showing the last good answer.`, warn: true });
  const ibkr = board.sources.find((s) => s.id === 'ibkr');
  if (ibkr && ibkr.ok === false) out.push({ id: 'ibkr', text: `IBKR: ${ibkr.error}`, warn: true });
  if (board.period !== wanted) {
    out.push({
      id: 'period',
      text: `Loading ${PERIOD_LABEL[wanted]} -- showing ${PERIOD_LABEL[board.period]} until it answers.`,
    });
  }
  if (board.loading) out.push({ id: 'loading', text: GLOBAL_LOADING });
  const waiting = waitingWords(board.budget);
  if (waiting) out.push({ id: 'waiting', text: waiting });
  return out;
}
