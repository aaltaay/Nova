/**
 * The Forex page's notes, on one line in its head (ADR 062; the page never scrolls): a failed poll, IBKR's own error,
 * another period still loading, the first reads, the weekend, and what the reads wait for -- with IBKR's history
 * requests left against the number Forex reads above.
 */
import type { Note } from '../world_board/controls';
import { until } from '../world_board/format';
import {
  FOREX_CLOSED, FOREX_LOADING, FOREX_WAITING_HISTORY_FIRST, FOREX_WAITING_LINES, PERIOD_LABEL,
} from './constants';
import type { Budget, ForexBoard, Period } from './types';

export function waitingWords(budget: Budget): string | null {
  if (budget.waiting === 'lines') return FOREX_WAITING_LINES;
  if (budget.waiting !== 'history') return null;
  const left = budget.history_left;
  return left == null
    ? `Waiting its turn for IBKR history (${FOREX_WAITING_HISTORY_FIRST}).`
    : `Waiting its turn for IBKR history: ${left} requests left this 10 minutes, Forex reads above `
      + `${budget.history_headroom} (${FOREX_WAITING_HISTORY_FIRST}).`;
}

export function statusNotes(board: ForexBoard, wanted: Period, error: string | null): Note[] {
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
  if (!board.fx_day.open) {
    out.push({ id: 'closed', text: `${FOREX_CLOSED}: Friday's day shown, opens ${until(board.fx_day.next_open_at, board.generated_at)}.` });
  }
  if (board.loading) out.push({ id: 'loading', text: FOREX_LOADING });
  const waiting = waitingWords(board.budget);
  if (waiting) out.push({ id: 'waiting', text: waiting });
  return out;
}
