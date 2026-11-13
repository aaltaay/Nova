/**
 * The account as the phone's Home and Account screens show it. It derives nothing of its own: it is
 * the desk's Account page read (pages/AccountPage.tsx) -- the IBKR summary on Live, Nova's practice
 * ledger on Paper and Sim, Paper's two books (ADR 069) -- gathered by the same helpers, so a figure
 * on the phone is the figure on the desk.
 */
import { useMemo } from 'react';
import { useAccountHistory } from '../account/accountHistoryResource';
import type { PracticeHistory } from '../account/accountHistoryTypes';
import { liveCommissionsToday, liveFillRows, practiceFillRows, type AccountFillRow } from '../account/accountLive';
import { positionsByOwner, positionsFromIbkr, positionsFromPractice, type AccountPosition } from '../account/accountPositions';
import { ALL_VIEW, daySplits, shows, viewBookDay, viewHistory, type DaySplit, type OwnerView } from '../account/ownerView';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { figuresFromPractice, figuresFromSummary, type HeaderAccountFigures } from '../components/headerAccountFigures';
import type { AccountRange } from '../constantGroups/account_page';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { resolveDeskVenue } from '../ibkr/deskVenue';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import type { IbkrOrder } from '../ibkr/types';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { isPracticeVenue } from '../practice/practiceAccountModel';
import { usePracticeAccount } from '../practice/practiceAccountResource';
import type { PracticeBooks } from '../practice/practiceTypes';
import { useSimAccountClock } from '../practice/useSimAccountClock';
import { useWorkspace } from '../workspace';

export interface PhoneAccount {
  /** The venue the numbers belong to: the desk's, Live while it is not known. */
  venue: DeskVenue;
  figures: HeaderAccountFigures;
  /** One row per holder on Paper (yours, then each bot's); one row per stock elsewhere. Narrowed to `view`. */
  positions: AccountPosition[];
  /** Working orders on the venue. */
  working: IbkrOrder[];
  /** Today's fills, newest first, narrowed to `view`. */
  fills: AccountFillRow[];
  /** Paper's two books; null on Live and Sim. */
  books: PracticeBooks | null;
  /** Open P&L of the view (the book's on Paper, the account's otherwise). */
  openPnl: number | null;
  /** Today's net of the view. */
  dayPnl: number | null;
  realizedToday: number | null;
  commissionsToday: number | null;
  /** Today's ledger history for the curve; null on Live (IBKR sends none) or before it loads. */
  history: PracticeHistory | null;
  /** The ledger over the chart's range, narrowed to `view`; today's while the range is 1D. */
  rangeHistory: PracticeHistory | null;
  /** Every day the ledger and its archives hold, narrowed to `view`: the calendar. Null unless asked for. */
  calendar: PracticeHistory | null;
  /** Each date's yours and the bots' (Paper, All); null with no split or no calendar. */
  daySplits: ReadonlyMap<string, DaySplit> | null;
  /** Why the calendar has nothing to show; null while it has. */
  calendarAbsence: string | null;
  /** "Now" for the curve: the Sim playhead on Sim, the clock otherwise. Epoch seconds. */
  nowTs: number;
  /**
   * Why the account on screen is not current; null while it is. The desk keeps the last rows it read when a read
   * fails (a Gateway that dropped, a ledger that did not answer), so this is set while rows are still shown.
   */
  error: string | null;
}

/** Said when a read is stale and the desk gave no words of its own for it. */
export const LAST_KNOWN = 'Last known account: Nova is not answering now.';

export interface PhoneAccountAsk {
  /** The chart's range; the day by default. */
  range?: AccountRange;
  /** Read every day too (the calendar). Off by default: Home never needs it. */
  calendar?: boolean;
}

const NO_CALENDAR_ON_LIVE = "IBKR sends no day-by-day history. The calendar is Paper's and Sim's.";

export function usePhoneAccount(view: OwnerView = ALL_VIEW, ask: PhoneAccountAsk = {}): PhoneAccount {
  const { ibkrMode, ibkrConnected } = useWorkspace();
  const status = useIbkrStatus();
  const resolved = resolveDeskVenue(status, ibkrMode);
  const venue: DeskVenue = isPracticeVenue(resolved) ? resolved : 'live';
  const practiceVenue = isPracticeVenue(venue) ? venue : null;
  const ibkr = useIbkrAccountContext();
  const practice = usePracticeAccount(practiceVenue);
  const { orders: closedOrders } = useClosedOrders(ibkrConnected);
  const history = useAccountHistory(practiceVenue, '1D');
  const ranged = useAccountHistory(practiceVenue, ask.range ?? '1D');
  const every = useAccountHistory(ask.calendar ? practiceVenue : null, 'ALL');
  const simClock = useSimAccountClock(practiceVenue === 'sim');

  const ledger = practiceVenue && practice.data?.venue === practiceVenue ? practice.data : null;
  const figures = ledger ? figuresFromPractice(ledger) : figuresFromSummary(ibkr.summary);
  const books = practiceVenue === 'paper' ? ledger?.books ?? null : null;
  const shown = books ? view : ALL_VIEW;
  const hist = history.data && history.data.venue === practiceVenue ? history.data : null;
  const viewed = useMemo(() => viewHistory(hist, shown), [hist, shown]);
  const rangeHist = ranged.data && ranged.data.venue === practiceVenue ? ranged.data : null;
  const viewedRange = useMemo(() => viewHistory(rangeHist, shown), [rangeHist, shown]);
  const everyHist = every.data && every.data.venue === practiceVenue ? every.data : null;
  const viewedEvery = useMemo(() => viewHistory(everyHist, shown), [everyHist, shown]);
  const splits = useMemo(() => (books && shown.book === 'all' ? daySplits(everyHist) : null), [books, shown, everyHist]);

  const positions = useMemo(() => {
    if (books && ledger) return positionsByOwner(ledger.positions).filter((p) => shows(shown, p.owner, p.bot));
    return ledger ? positionsFromPractice(ledger.positions) : positionsFromIbkr(ibkr.positions);
  }, [books, ledger, ibkr.positions, shown]);

  const working = useMemo(
    () => ibkr.orders.filter((o) => !books || shows(shown, o.owner ?? 'you', o.bot)),
    [ibkr.orders, books, shown],
  );

  const liveOrders = useMemo(
    () => (practiceVenue ? [] : [...ibkr.orders, ...closedOrders]),
    [practiceVenue, ibkr.orders, closedOrders],
  );
  const fills = useMemo(() => {
    const rows = practiceVenue ? practiceFillRows(viewed?.fills ?? []) : liveFillRows(liveOrders);
    return [...rows].sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
  }, [practiceVenue, viewed, liveOrders]);

  const bookDay = viewBookDay(books, shown);
  return {
    venue,
    figures,
    positions,
    working,
    fills,
    books,
    openPnl: bookDay ? bookDay.unrealized_pnl : figures.openPnl,
    dayPnl: bookDay ? bookDay.day_pnl : figures.dayPnl,
    realizedToday: bookDay ? bookDay.realized_today : figures.realizedPnl,
    commissionsToday: bookDay
      ? bookDay.commissions_today
      : practiceVenue ? figures.feesToday : liveCommissionsToday(liveOrders),
    history: viewed,
    rangeHistory: viewedRange,
    calendar: viewedEvery,
    daySplits: splits,
    calendarAbsence: viewedEvery
      ? null
      : !practiceVenue ? NO_CALENDAR_ON_LIVE : every.error ? `The ledger did not answer: ${every.error}` : 'Reading the ledger…',
    nowTs: simClock.nowTs ?? Date.now() / 1000,
    // Paper and Sim read the ledger for the account and positions, and the desk's account poll for working orders.
    error: (practiceVenue ? practice.error : null) ?? ibkr.error
      ?? ((practiceVenue && practice.stale === true) || ibkr.stale ? LAST_KNOWN : null),
  };
}
