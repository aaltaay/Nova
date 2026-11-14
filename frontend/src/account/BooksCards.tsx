/**
 * Three books, one account (ADR 072, mockup three-books v1 items 2-3): You, Claude and The brain, each with its P&L
 * today and its realized this month ("Nov +$539.54"; "no trades yet" for a trader that never traded), then
 * Earlier bots as a slim line -- only while it has a number this month, history only -- then each AI trader's own
 * budget: what its open shares at the mark and its working entries hold of its limit. A card the view does not show
 * is dimmed.
 */
import {
  OWNER_BUDGET_NOTE,
  OWNER_BUDGETS,
  OWNER_EARLIER_HISTORY,
  OWNER_NAMES,
  OWNER_NO_TRADES_YET,
  OWNER_THREE_BOOKS,
  OWNER_TODAY,
  AI_TRADERS,
  OWNERS,
  ownerBudgetHeld,
  ownerBudgetLabel,
  type Owner,
} from '../constantGroups/owners';
import { formatSignedMoney } from '../components/globalBarMoney';
import type { PracticeBooks } from '../practice';
import { toneClass, toneOf } from './accountBits';
import type { DaySplit, OwnerView } from './ownerView';

interface Props {
  books: PracticeBooks;
  view: OwnerView;
  /** Each book's realized this month, from the calendar's days; null while it has not answered. */
  month: DaySplit | null;
  /** This month's short name ("Nov"). */
  monthName: string;
  /** The books that ever traded (the ledger's holders); null while the history has not answered. */
  traded: ReadonlySet<Owner> | null;
  hidden: boolean;
  hiddenText: string;
}

const CARDS: readonly Owner[] = ['you', 'claude', 'brain'];
const CENT = 0.005;

/** Day's P&L and Fills today split by book (mockup three-books v1): the four books' own figures, today. */
export interface BookRows {
  dayPnl: DaySplit;
  fills: DaySplit;
}

export function bookRows(books: PracticeBooks): BookRows {
  const pick = (key: 'day_pnl' | 'fills_today'): DaySplit => ({
    you: books.you[key], claude: books.claude[key], brain: books.brain[key], earlier_bots: books.earlier_bots[key],
  });
  return { dayPnl: pick('day_pnl'), fills: pick('fills_today') };
}

/** One row's split under its figure: You, Claude, The brain, and Earlier bots only while it has a number. */
export function BookSplitMini({ split, money, testId }: { split: DaySplit; money: boolean; testId: string }) {
  const shown = OWNERS.filter((o) => o !== 'earlier_bots' || Math.abs(split[o]) >= CENT);
  return (
    <span className="acct-split-mini" data-testid={testId}>
      {shown.map((o) => (
        <span key={o} title={OWNER_NAMES[o]} data-owner={o}>
          <i className={`acct-owner__dot is-${o}`} aria-hidden />
          <span className="acct-num">{money ? formatSignedMoney(split[o]) : split[o].toLocaleString('en-US')}</span>
        </span>
      ))}
    </span>
  );
}

function MonthLine({ value, monthName }: { value: number; monthName: string }) {
  return <>{monthName} <span className={`acct-num ${toneClass(toneOf(value))}`}>{formatSignedMoney(value)}</span></>;
}

function Card({ book, today, month, monthName, never, dim, hidden, hiddenText }: {
  book: Owner; today: number; month: number | null; monthName: string; never: boolean; dim: boolean; hidden: boolean;
  hiddenText: string;
}) {
  return (
    <div className={`acct-book is-${book}${dim ? ' is-dim' : ''}`} data-testid={`account-book-${book}`}>
      <div className="acct-book__k"><i className={`acct-owner__dot is-${book}`} aria-hidden />{OWNER_NAMES[book]}</div>
      <div className={`acct-book__v acct-num ${hidden ? '' : toneClass(toneOf(today))}`}>{hidden ? hiddenText : formatSignedMoney(today)}</div>
      <div className="acct-book__s">{OWNER_TODAY}</div>
      <div className="acct-book__s" data-testid={`account-book-${book}-month`}>
        {never ? OWNER_NO_TRADES_YET : month != null && !hidden ? <MonthLine value={month} monthName={monthName} /> : ' '}
      </div>
    </div>
  );
}

export function BooksCards({ books, view, month, monthName, traded, hidden, hiddenText }: Props) {
  const dim = (book: Owner) => view.book !== 'all' && view.book !== book;
  const earlierMonth = month?.earlier_bots ?? 0;
  const earlierShown = Math.abs(earlierMonth) >= CENT || Math.abs(books.earlier_bots.day_pnl) >= CENT;
  return (
    <div data-testid="account-books">
      <div className="acct-books__cap">{OWNER_THREE_BOOKS}</div>
      <div className="acct-books">
        {CARDS.map((book) => (
          <Card key={book} book={book} today={books[book].day_pnl} month={month?.[book] ?? null} monthName={monthName}
            never={traded != null && !traded.has(book) && books[book].fills_today === 0}
            dim={dim(book)} hidden={hidden} hiddenText={hiddenText} />
        ))}
      </div>
      {earlierShown && (
        <div className={`acct-erow${dim('earlier_bots') ? ' is-dim' : ''}`} data-testid="account-book-earlier_bots">
          <i className="acct-owner__dot is-earlier_bots" aria-hidden />
          <b>{OWNER_NAMES.earlier_bots}</b>
          {!hidden && <span><MonthLine value={earlierMonth} monthName={monthName} /></span>}
          <span className="acct-erow__note">{OWNER_EARLIER_HISTORY}</span>
        </div>
      )}
      <div className="acct-budgets" data-testid="account-budgets" title={OWNER_BUDGET_NOTE}>
        <div className="acct-books__cap">{OWNER_BUDGETS}</div>
        {AI_TRADERS.map((trader) => {
          const budget = books[trader].budget_usd;
          const used = books[trader].budget_used_usd;
          const share = budget > 0 ? Math.min(1, Math.max(0, used / budget)) : 1;
          return (
            <div key={trader} data-testid={`account-budget-${trader}`}>
              <div className="acct-budget">
                <i className={`acct-owner__dot is-${trader}`} aria-hidden />
                <span className="acct-budget__k">{ownerBudgetLabel(trader)}</span>
                <span className="acct-budget__v acct-num">{ownerBudgetHeld(used, budget)}</span>
              </div>
              <div className={`acct-budget__meter is-${trader}`} role="meter" aria-valuemin={0} aria-valuemax={budget}
                aria-valuenow={used} aria-label={ownerBudgetLabel(trader)}>
                <i style={{ width: `${(share * 100).toFixed(1)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
