/**
 * All / You / Claude / The brain / Earlier bots on the Account page's tab row (ADR 072, mockup three-books v1 item
 * 1). Earlier bots opens a pick of one retired bot by name -- only the bots that traded. On Live it reads You,
 * disabled with its reason: Claude and the brain never trade Live. Paper and Sim get the same switch (Sim keeps the
 * books too). The same switch serves Overview and Reports, one pick for both; on Reports each pick counts its
 * closed trades (mockup reports-v1 item 1). The page opens on All.
 */
import { useState } from 'react';
import {
  OWNER_ALL_BOTS,
  OWNER_BOOKS,
  OWNER_LIVE_WHY,
  OWNER_SWITCH_ARIA,
  OWNER_SWITCH_LABELS,
  ownerBotName,
  ownerTradeCount,
  type Owner,
} from '../constantGroups/owners';
import type { OwnerView } from './ownerView';

/** Closed trades behind each pick (Reports): every earlier bot's together, each one's own, and each book's. */
export interface BotCounts {
  all: number;
  byBot: Record<string, number>;
  /** Each book's closed trades, drawn beside its pick; absent: no count. */
  books?: Partial<Record<Owner, number>>;
}

interface Props {
  view: OwnerView;
  onView: (view: OwnerView) => void;
  /** The retired bots that traded in the page's history, first-fill order. */
  bots: string[];
  live: boolean;
  /** Reports' counts; a bot counted there joins the menu. */
  counts?: BotCounts | null;
}

const dot = (book: string) => <i className={`acct-owner__dot is-${book}`} aria-hidden />;

const count = (n: number) => <span className="acct-owner__count">{ownerTradeCount(n)}</span>;

export function OwnerSwitch({ view, onView, bots, live, counts }: Props) {
  const [open, setOpen] = useState(false);
  if (live) {
    return (
      <div className="acct-owner" role="group" aria-label={OWNER_SWITCH_ARIA} data-testid="account-owner-switch">
        <button type="button" className="acct-owner__item is-on" disabled aria-disabled="true" data-why={OWNER_LIVE_WHY}
          title={OWNER_LIVE_WHY} data-testid="account-owner-you">
          {dot('you')}{OWNER_SWITCH_LABELS.you}
        </button>
      </div>
    );
  }
  const pick = (next: OwnerView) => {
    setOpen(false);
    onView(next);
  };
  const listed = counts ? [...bots, ...Object.keys(counts.byBot).filter((b) => !bots.includes(b))] : bots;
  return (
    <div className="acct-owner" role="group" aria-label={OWNER_SWITCH_ARIA} data-testid="account-owner-switch">
      {OWNER_BOOKS.map((book) => {
        const on = view.book === book;
        const earlier = book === 'earlier_bots';
        const label = earlier && on && view.bot ? ownerBotName(view.bot) : OWNER_SWITCH_LABELS[book];
        const n = book === 'all' ? undefined : counts?.books?.[book];
        return (
          <button key={book} type="button" aria-pressed={on} className={`acct-owner__item${on ? ' is-on' : ''}`}
            aria-haspopup={earlier ? 'menu' : undefined} aria-expanded={earlier ? open : undefined}
            data-testid={`account-owner-${book}`}
            onClick={() => (earlier ? setOpen((o) => !o) : pick({ book, bot: null }))}>
            {dot(book === 'all' ? 'all' : book)}{label}
            {n != null && <i className="acct-owner__n">{n.toLocaleString('en-US')}</i>}
            {earlier && <span className="acct-owner__caret" aria-hidden>▾</span>}
          </button>
        );
      })}
      {open && (
        <div className="acct-owner__menu" role="menu" data-testid="account-owner-menu">
          <button type="button" role="menuitem"
            className={`acct-owner__opt${view.book === 'earlier_bots' && !view.bot ? ' is-on' : ''}`}
            data-testid="account-owner-bot-all" onClick={() => pick({ book: 'earlier_bots', bot: null })}>
            {dot('earlier_bots')}{OWNER_ALL_BOTS}{counts && count(counts.all)}
          </button>
          {listed.map((bot) => (
            <button key={bot} type="button" role="menuitem"
              className={`acct-owner__opt${view.book === 'earlier_bots' && view.bot === bot ? ' is-on' : ''}`}
              data-testid={`account-owner-bot-${bot}`} onClick={() => pick({ book: 'earlier_bots', bot })}>
              {dot('earlier_bots')}{ownerBotName(bot)}{counts && count(counts.byBot[bot] ?? 0)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
