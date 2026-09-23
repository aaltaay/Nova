/**
 * The bot's own P&L on the practice day: its fills in Nova's practice ledger
 * (GET /api/practice/history, read from each fill's `source` / `bot_id`
 * stamp, never inferred), realized net of fees and commission. Live keeps no
 * practice ledger, so there it is a stated absence, never $0.
 */
import { todayPracticeDate } from '../account/accountFigures';
import { useAccountHistory } from '../account/accountHistoryResource';
import type { HistoryFill } from '../account/accountHistoryTypes';
import type { PracticeVenue } from '../constantGroups/practice';

/** Sum of today's bot fills: realized (already net of fees) less commission. */
export function botPnlOn(fills: readonly HistoryFill[], today: string): number {
  let total = 0;
  for (const fill of fills) {
    if (fill.source !== 'bot' && !fill.bot_id) continue;
    if (todayPracticeDate(new Date(fill.ts * 1000)) !== today) continue;
    total += (Number(fill.realized) || 0) - (Number(fill.commission) || 0);
  }
  return total;
}

/** Null on Live or while the ledger has not answered for this venue. */
export function useBotPnlToday(practiceVenue: PracticeVenue | null, today: string): number | null {
  const history = useAccountHistory(practiceVenue, '1D');
  const data = history.data && history.data.venue === practiceVenue ? history.data : null;
  return data ? botPnlOn(data.fills, today) : null;
}
