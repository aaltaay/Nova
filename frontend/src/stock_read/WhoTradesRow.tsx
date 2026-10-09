/**
 * "Who trades SYMBOL", directly above Level 2 (ADR 037): Buy (You | Bot) and Sell (You | Bot), the mode
 * they make, and under them everything the view says (ADR 042 draft): a refused change, every note that
 * keeps Nova from acting (each toned; none hidden behind the first), Nova's automatic trades today against
 * the day's cap, and the stock's last event -- the bot's skips on it included. A locked side carries its
 * reason; the same switch is the chip on the 1-minute chart.
 */
import { useState } from 'react';
import { hotListActions, listedOn, useHotList } from '../hot_list';
import type { DepthMarker } from '../ibkr';
import { tipProps, whyProps } from '../ux';
import { STOCK_MODE_COLORS, WHO_TRADES_NOTES_SHOWN } from './constants';
import { heldAnyQty, shortQty } from './momentShort';
import { capUsedText } from './novaPromise';
import { useStockReadContext, type StockReadContextValue } from './StockReadContext';
import { hhmmssEt } from './timeWords';
import type { StockModeView, StockSide } from './types';
import { sideLine, whoAnswer } from './whoAnswer';
import { MODE_NAMES, MODE_SIDES, modeSentence, switchLock } from './whoTradesModel';
import './whoTrades.css';
import './shortRead.css';

/** The desk's own reason to wait before a change: an old backend, a read in flight, a save in flight. */
export function switchPending(ctx: StockReadContextValue): string | null {
  const who = ctx.who;
  if (who.unavailable) return 'This backend is older than the desk and cannot say who trades. Reload the backend.';
  if (who.busy) return who.busy;
  return null;
}

function SideSwitch({ label, value, lockYou, lockNova, onPick, testId }: {
  label: string;
  value: StockSide;
  lockYou: string | null;
  lockNova: string | null;
  onPick: (side: StockSide) => void;
  testId: string;
}) {
  const button = (side: StockSide, locked: string | null) => {
    const on = value === side;
    return (
      <button
        type="button"
        className={`sr-who__side sr-who__side--${side}${on ? ' sr-who__side--on' : ''}`}
        aria-pressed={on}
        disabled={!on && locked !== null}
        {...whyProps(!on && locked !== null, locked)}
        onClick={() => {
          if (!on) onPick(side);
        }}
        data-testid={`${testId}-${side}`}
      >
        {side === 'nova' && !on && locked !== null ? '🔒 ' : ''}
        {side === 'you' ? 'You' : 'Bot'}
      </button>
    );
  };
  return (
    <span className="sr-who__switch" role="group" aria-label={label} data-testid={testId}>
      <span className="sr-who__side-label">{label}</span>
      {button('you', lockYou)}
      {button('nova', lockNova)}
    </span>
  );
}

/** Nova's automatic trades today (longs and shorts) against the day's shared cap, in a mode where Nova enters
 * by itself. */
function entriesLine(view: StockModeView | null): { text: string; tip: string; used: boolean } | null {
  if (!view || (view.mode !== 'bot' && view.mode !== 'auto_entry') || !view.entries_today) return null;
  const { count, cap } = view.entries_today;
  const used = capUsedText(view);
  return {
    text: `Nova's automatic trades today: ${count}${cap !== null ? ` of ${cap}` : ''}`,
    tip: used ?? 'The bot and Auto-entry share one count a day on this venue, longs and shorts together; an entry that '
      + 'missed gives its place back.',
    used: used !== null,
  };
}

/** Every note, the first `WHO_TRADES_NOTES_SHOWN` (warnings before information) on their own lines and
 * the rest folded into one line that names them on hover and opens them on a click: Level 2 keeps its room
 * and no reason is hidden. */
export function NotesList({ notes, sym }: { notes: StockModeView['notes']; sym: string }) {
  const [open, setOpen] = useState(false);
  const ordered = [...notes.filter(n => n.tone !== 'info'), ...notes.filter(n => n.tone === 'info')];
  const shown = open ? ordered : ordered.slice(0, WHO_TRADES_NOTES_SHOWN);
  const rest = ordered.slice(shown.length);
  return (
    <ul className="sr-who__notes" aria-label={`What keeps Nova from acting on ${sym}`} data-testid="who-trades-notes">
      {shown.map((n, i) => (
        <li key={`${n.id}:${i}`} className={`sr-who__note sr-who__note--${n.tone}`} {...tipProps(n.text)}
          data-testid={`who-trades-note-${n.id}`}>
          {n.text}
        </li>
      ))}
      {rest.length > 0 && (
        <li className="sr-who__note sr-who__note--more">
          <button type="button" className="sr-who__more" onClick={() => setOpen(true)}
            {...tipProps(rest.map(n => n.text).join('\n'), `${rest.length} more reason${rest.length === 1 ? '' : 's'}`)}
            data-testid="who-trades-notes-more">
            +{rest.length} more reason{rest.length === 1 ? '' : 's'} (hover, or click to open)
          </button>
        </li>
      )}
      {open && ordered.length > WHO_TRADES_NOTES_SHOWN && (
        <li className="sr-who__note sr-who__note--more">
          <button type="button" className="sr-who__more" onClick={() => setOpen(false)} data-testid="who-trades-notes-less">
            Show fewer
          </button>
        </li>
      )}
    </ul>
  );
}

/** The ★: today's hot list (ADR 044, amended 2026-10-06). Watching only: who trades the stock is its Buy / Sell. */
function HotStar({ sym, onError }: { sym: string; onError: (message: string | null) => void }) {
  const hot = useHotList();
  const listed = listedOn(hot.view, sym);
  const entry = hot.view?.entries.find(e => e.symbol === sym) ?? null;
  const why = hot.busy ? 'Saving the hot list…' : hot.view ? null : (hot.error ?? 'Reading today\'s hot list…');
  const auto = listed === true && entry?.how === 'auto';
  const tip = listed
    ? `On today's hot list (${auto ? 'an auto ☆: the top of the Gainers board' : 'your ★'}). The scanners follow it all `
      + 'day and you get its toasts. Watching only: the bot trades it only where Buy / Sell says Bot. Click to take it off.'
    : 'Not on today\'s hot list. Star it and the scanners follow it all day, with a toast when it alerts. A star never '
      + 'lets the bot trade it: that is Buy / Sell.';
  return (
    <button
      type="button"
      className={`sr-who__star${listed ? ' sr-who__star--on' : ''}${auto ? ' sr-who__star--auto' : ''}`}
      aria-pressed={listed === true}
      disabled={why !== null}
      {...(why ? whyProps(true, why) : tipProps(tip, listed ? 'On today\'s hot list' : 'Add to today\'s hot list'))}
      onClick={() => void (listed ? hotListActions.unstar(sym) : hotListActions.star(sym)).then(onError)}
      data-testid="who-trades-star"
    >
      {listed && !auto ? '★' : '☆'}
    </button>
  );
}

function WhoTradesRowView({ ctx }: { ctx: StockReadContextValue }) {
  const who = ctx.who;
  const [starError, setStarError] = useState<string | null>(null);
  const view = who.view;
  const sym = ctx.symbol;
  const mode = view?.mode ?? 'signal';
  const buy = view?.buy ?? 'you';
  const sell = view?.sell ?? 'you';
  const held = heldAnyQty(who.inputs);
  const pending = switchPending(ctx);
  const short = shortQty(who.inputs) > 0;
  const lock = (to: { buy: StockSide; sell: StockSide }) => switchLock(view, to, { symbol: sym, held, pending, short });
  const line = who.error ?? (who.unavailable ? pending : null);
  const notes = view?.notes ?? [];
  const entries = entriesLine(view);
  const event = view?.last_event ?? null;
  const tip = [modeSentence(mode, sym), ...notes.map(n => n.text)].join('\n');
  const answer = whoAnswer(sym, view, short ? shortQty(who.inputs) : 0);
  const sides = sideLine(view, ctx.readNow?.plan ?? null);
  return (
    <section className="sr-who" data-testid="who-trades" aria-label={`Who trades ${sym}`}>
      <div className="sr-who__row">
        <HotStar sym={sym} onError={setStarError} />
        <span className="sr-who__kicker" {...tipProps(`Who places each side of the trade on ${sym}: the Entry and the `
          + 'Exit, each You or Bot. With Entry on Bot, the strategy that triggers decides long or short.', `Who trades ${sym}`)}>
          <span className="sr-who__kicker-words">Who trades </span>
          {sym}
        </span>
        <SideSwitch
          label="Entry"
          value={buy}
          lockYou={lock({ buy: 'you', sell })}
          lockNova={lock({ buy: 'nova', sell })}
          onPick={side => void who.setSides(side, sell)}
          testId="who-trades-buy"
        />
        <SideSwitch
          label="Exit"
          value={sell}
          lockYou={lock({ buy, sell: 'you' })}
          lockNova={lock({ buy, sell: 'nova' })}
          onPick={side => (side === 'nova' && sell === 'you' && held > 0
            ? ctx.exitSheet.setOpen(true)                 // a stock you hold: "Nova takes the exit" (or the cover)
            : void who.setSides(buy, side))}
          testId="who-trades-sell"
        />
        <span className="sr-who__mode" {...tipProps(tip, `${MODE_NAMES[mode]} · ${MODE_SIDES[mode]}`)} data-testid="who-trades-mode">
          <i className="sr-who__dot" style={{ background: STOCK_MODE_COLORS[mode] }} aria-hidden="true" />
          {view ? MODE_NAMES[mode] : '…'}
        </span>
      </div>
      {answer && (
        <p className={`sr-who__answer sr-who__answer--${answer.tone}`} {...tipProps(answer.text)} data-testid="who-trades-answer">
          {answer.text}
        </p>
      )}
      {sides && (
        <p className="sr-who__answer sr-who__answer--sides" {...tipProps(sides)} data-testid="who-trades-sides">{sides}</p>
      )}
      {starError && (
        <p className="sr-who__note sr-who__note--bad" {...tipProps(starError)} data-testid="who-trades-star-error">{starError}</p>
      )}
      {line && (
        <p
          className={`sr-who__note sr-who__note--${who.error ? 'bad' : 'warn'}`}
          {...tipProps(line)}
          data-testid="who-trades-note"
        >
          {line}
        </p>
      )}
      {notes.length > 0 && <NotesList notes={notes} sym={sym} />}
      {entries && (
        <p className={`sr-who__note sr-who__note--${entries.used ? 'warn' : 'info'}`}
          {...tipProps(entries.tip, 'Nova\'s automatic trades today')} data-testid="who-trades-entries">
          {entries.text}
        </p>
      )}
      {event && (
        <p className={`sr-who__note sr-who__note--event-${event.tone}`} {...tipProps(event.text, `Last on ${sym}`)}
          data-testid="who-trades-event">
          <span className="sr-who__event-at">{hhmmssEt(event.ts)}</span> {event.text}
        </p>
      )}
    </section>
  );
}

/** The plan's ENTRY / STOP / TARGET for this tab's Level 2 -- a Sim replay's plan at the playhead on a replay
 * (ADR 052); none on the sample desk. */
export function useLevel2Markers(): readonly DepthMarker[] | undefined {
  const ctx = useStockReadContext();
  return ctx ? ctx.who.markers : undefined;
}

/** The row, on a Sim replay too (ADR 052: the bot trades a replay); nothing on the sample desk (no stock read). */
export function WhoTradesRow() {
  const ctx = useStockReadContext();
  if (!ctx) return null;
  return <WhoTradesRowView ctx={ctx} />;
}
