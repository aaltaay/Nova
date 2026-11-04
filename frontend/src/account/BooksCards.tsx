/**
 * Your book and the bots' book under the account's value (ADR 069, mockup v1 items 2-3): each book's P&L today
 * and this month, then how much of the bots' budget they hold. The card the view does not show is dimmed.
 */
import {
  OWNER_BOOK_BOTS,
  OWNER_BOOK_YOU,
  OWNER_BUDGET_LABEL,
  OWNER_BUDGET_NOTE,
  OWNER_MONTH,
  OWNER_TODAY,
  ownerBudgetHeld,
} from '../constantGroups/owners';
import { formatSignedMoney } from '../components/globalBarMoney';
import type { PracticeBooks } from '../practice';
import { toneClass, toneOf } from './accountBits';
import type { OwnerView } from './ownerView';

interface Props {
  books: PracticeBooks;
  view: OwnerView;
  /** Each book's realized this month, from the calendar's days; null while it has not answered. */
  month: { you: number; bots: number } | null;
  hidden: boolean;
  hiddenText: string;
}

function Card({ book, title, today, month, dim, hidden, hiddenText }: {
  book: 'you' | 'bots'; title: string; today: number; month: number | null; dim: boolean; hidden: boolean;
  hiddenText: string;
}) {
  return (
    <div className={`acct-book is-${book}${dim ? ' is-dim' : ''}`} data-testid={`account-book-${book}`}>
      <div className="acct-book__k"><i className={`acct-owner__dot is-${book}`} aria-hidden />{title}</div>
      <div className={`acct-book__v acct-num ${hidden ? '' : toneClass(toneOf(today))}`}>{hidden ? hiddenText : formatSignedMoney(today)}</div>
      <div className="acct-book__s">
        {OWNER_TODAY}
        {month != null && !hidden && <> · {OWNER_MONTH} <span className={`acct-num ${toneClass(toneOf(month))}`}>{formatSignedMoney(month)}</span></>}
      </div>
    </div>
  );
}

export function BooksCards({ books, view, month, hidden, hiddenText }: Props) {
  const budget = books.bots.budget_usd;
  const used = books.bots.budget_used_usd;
  const share = budget > 0 ? Math.min(1, Math.max(0, used / budget)) : 1;
  return (
    <div data-testid="account-books">
      <div className="acct-books">
        <Card book="you" title={OWNER_BOOK_YOU} today={books.you.day_pnl} month={month?.you ?? null}
          dim={view.book === 'bots'} hidden={hidden} hiddenText={hiddenText} />
        <Card book="bots" title={OWNER_BOOK_BOTS} today={books.bots.day_pnl} month={month?.bots ?? null}
          dim={view.book === 'you'} hidden={hidden} hiddenText={hiddenText} />
      </div>
      <div className="acct-budget" data-testid="account-bots-budget">
        <span className="acct-budget__k">{OWNER_BUDGET_LABEL}</span>
        <span className="acct-budget__v acct-num">{ownerBudgetHeld(used, budget)}</span>
      </div>
      <div className="acct-budget__meter" role="meter" aria-valuemin={0} aria-valuemax={budget} aria-valuenow={used}
        aria-label={OWNER_BUDGET_LABEL}>
        <i style={{ width: `${(share * 100).toFixed(1)}%` }} />
      </div>
      <div className="acct-budget__note">{OWNER_BUDGET_NOTE}</div>
    </div>
  );
}
