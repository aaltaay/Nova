/**
 * All / You / Bots on the Account page's tab row (ADR 069, mockup v1 item 1). Bots opens a pick of one bot by
 * name. On Live it reads You, disabled with its reason: every Live trade is yours. Sim has no switch. The same
 * switch serves Overview and Reports, one pick for both; on Reports the pick counts each bot's closed trades
 * (mockup reports-v1 item 1).
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
} from '../constantGroups/owners';
import type { OwnerView } from './ownerView';

/** Closed trades behind each pick of the Bots menu: every bot's together and each bot's own. */
export interface BotCounts {
  all: number;
  byBot: Record<string, number>;
}

interface Props {
  view: OwnerView;
  onView: (view: OwnerView) => void;
  /** The bots that traded in the page's history, first-fill order. */
  bots: string[];
  live: boolean;
  /** Reports' counts for the menu; a bot counted there joins the list. */
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
        const label = book === 'bots' && view.book === 'bots' && view.bot ? ownerBotName(view.bot) : OWNER_SWITCH_LABELS[book];
        return (
          <button key={book} type="button" aria-pressed={on} className={`acct-owner__item${on ? ' is-on' : ''}`}
            data-testid={`account-owner-${book}`}
            onClick={() => (book === 'bots' ? setOpen((o) => !o) : pick({ book, bot: null }))}>
            {dot(book)}{label}{book === 'bots' && <span className="acct-owner__caret" aria-hidden>▾</span>}
          </button>
        );
      })}
      {open && (
        <div className="acct-owner__menu" role="menu" data-testid="account-owner-menu">
          <button type="button" role="menuitem" className={`acct-owner__opt${view.book === 'bots' && !view.bot ? ' is-on' : ''}`}
            data-testid="account-owner-bot-all" onClick={() => pick({ book: 'bots', bot: null })}>
            {dot('bots')}{OWNER_ALL_BOTS}{counts && count(counts.all)}
          </button>
          {listed.map((bot) => (
            <button key={bot} type="button" role="menuitem" className={`acct-owner__opt${view.bot === bot ? ' is-on' : ''}`}
              data-testid={`account-owner-bot-${bot}`} onClick={() => pick({ book: 'bots', bot })}>
              {dot(bot === 'claude' ? 'claude' : 'bots')}{ownerBotName(bot)}{counts && count(counts.byBot[bot] ?? 0)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
