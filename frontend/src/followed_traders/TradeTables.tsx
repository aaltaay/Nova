/**
 * A trader's trades, as the approved page drew them (2026-10-13, "E2"), in one table since 2026-10-15 (operator: "make
 * this more compact"): each open position an OPEN row on top, striped blue, then the closed trades striped by result. A time the feed did not see reads "by HH:MM:SS" (open when capture
 * started) or a window; an exit seen only in a window is IBKR's low–high, marked est.; a price Nova has not got says
 * why on hover, and Proof shows the trade's screenshots on hover (ProofLink). Closed rows drop to one line
 * (`compact`) and their oldest fold into "+N earlier" when the page would not fit otherwise; open rows never fold. A
 * ticker opens the stock in the Trader; another feature may mark an open row (slots.ts). Nothing here places an order.
 */
import { tipProps } from '../ux/hoverTip';
import {
  FT_EST,
  FT_EST_TIP,
  FT_EXIT_PENDING,
  FT_NOW,
  FT_OFF_AIR_CLOSE,
  FT_OFF_AIR_CLOSE_TIP,
  FT_OPEN_CHIP,
  FT_OPEN_END_TIP,
  FT_OPEN_ROW_TIP,
  FT_PL_COLUMN,
  FT_PROOF,
} from './constants';
import { DASH, entered, etTime, exitPrice, exited, held, price } from './format';
import { PlCell, ResultWord, SideChip, Ticker, TickerMark } from './parts';
import { ProofLink } from './ProofLink';
import { useFollowedSlots } from './slots';
import type { FollowedTrade } from './types';

function TimeIn({ t }: { t: FollowedTrade }) {
  const unseen = !t.entry.known || t.entry.since_ts !== null;
  const tip = !t.entry.known ? 'Already open when capture started: its real entry time is unknown' :
    t.entry.since_ts !== null ? 'The entry happened while the feed could not see the bar, somewhere in this window' : null;
  return <span className={unseen ? 'ft-muted' : undefined} {...tipProps(tip)}>{entered(t.entry)}</span>;
}

function TimeOut({ t }: { t: FollowedTrade }) {
  if (t.status === 'unknown') return <span className="ft-muted" {...tipProps('The feed saw this position open again without seeing it close')}>not seen</span>;
  if (!t.exit) return <span className="ft-muted">{DASH}</span>;
  const win = t.exit.from_ts !== null;
  const time = (
    <span className={win ? 'ft-window' : undefined} {...tipProps(win ? 'The exit happened while the feed could not see the bar, somewhere in this window' : null)}>
      {exited(t.exit)}
    </span>
  );
  if (!t.left_bar) return time;
  return (
    <>{time} <span className="ft-note" data-testid={`ft-off-air-close-${t.id}`} {...tipProps(FT_OFF_AIR_CLOSE_TIP)}>{FT_OFF_AIR_CLOSE}</span></>
  );
}

function Entry({ t, compact }: { t: FollowedTrade; compact: boolean }) {
  const added = t.entry.first_price !== t.entry.avg_price;
  const was = `avg, was ${price(t.entry.first_price)}`;
  return (
    <>
      <span className="ft-mono ft-strong">{price(t.entry.avg_price)}</span>
      {added && <span className="ft-note ft-note--warn" {...tipProps(compact ? `The trader added: ${was}` : null)}>{compact ? 'avg' : was}</span>}
    </>
  );
}

function Exit({ t }: { t: FollowedTrade }) {
  const exit = t.exit;
  if (!exit) return <span className="ft-muted">{DASH}</span>;
  if (exit.state === 'range') {
    return <span className="ft-mono ft-strong" {...tipProps(FT_EST_TIP)}>{exitPrice(exit)} <span className="ft-est">{FT_EST}</span></span>;
  }
  const tip = exit.state === 'at' && exit.trade_ts ? `IBKR’s last trade by the exit, printed ${etTime(exit.trade_ts)} ET` : exit.why;
  return (
    <span className={`ft-mono${exit.state === 'at' ? ' ft-strong' : ' ft-muted'}`} {...tipProps(tip)}>
      {exit.state === 'pending' && !exit.why ? FT_EXIT_PENDING : exitPrice(exit)}
    </span>
  );
}

function Now({ t }: { t: FollowedTrade }) {
  const now = t.now;
  if (now?.state === 'live') return <span className="ft-mono ft-strong">{price(now.price)}</span>;
  const why = now?.why ?? (now?.state === 'waiting' ? 'opening IBKR’s line' : null);
  return <span className="ft-mono ft-muted" {...tipProps(why)}>{now?.state === 'waiting' ? '…' : DASH}</span>;
}

/** One open position, on top of the table: what they hold, the price now and what it is worth at $1,000, how long. On
 *  a past day it is what was open at the day's end, with no "now". */
function OpenRow({ t, onProof, compact, isToday }: { t: FollowedTrade; onProof: (id: string) => void; compact: boolean; isToday: boolean }) {
  const { OpenBadge } = useFollowedSlots();
  return (
    <tr className="ft-closed ft-closed--open" data-testid={`ft-row-${t.id}`}>
      <td><span className="ft-result-word" {...tipProps(isToday ? FT_OPEN_ROW_TIP : FT_OPEN_END_TIP)}>{FT_OPEN_CHIP}</span></td>
      <td>
        <Ticker symbol={t.symbol} className="ft-ticker" /><TickerMark ticker={t.ticker} />
        {isToday && OpenBadge && <OpenBadge trade={t} />}
      </td>
      <td><SideChip side={t.side} /></td>
      <td><TimeIn t={t} /> → <span className="ft-muted">{isToday ? FT_NOW : DASH}</span></td>
      <td>
        <span className="ft-prices">
          <Entry t={t} compact={compact} /> → <Now t={t} />{isToday && <span className="ft-muted ft-xs">{FT_NOW}</span>}
        </span>
      </td>
      <td><PlCell trade={t} inline /></td>
      <td>{held(t.held)}</td>
      <td className="ft-right"><ProofLink t={t} onProof={onProof} /></td>
    </tr>
  );
}

interface TradesProps {
  /** Open positions, drawn first and never folded. */
  open?: FollowedTrade[];
  trades: FollowedTrade[];
  onProof: (tradeId: string) => void;
  compact?: boolean;
  /** How many of the oldest are folded into "+N earlier". */
  folded?: number;
  onShowAll?: () => void;
  /** Today: an open row's price is now. */
  isToday?: boolean;
}

/** Open positions on top, then the closed trades, newest exit first. */
export function TradesTable({ open = [], trades, onProof, compact = false, folded = 0, onShowAll, isToday = true }: TradesProps) {
  const shown = folded > 0 ? trades.slice(0, Math.max(0, trades.length - folded)) : trades;
  return (
    <table className={`ft-table ft-table--closed${compact ? ' is-compact' : ''}`}>
      <colgroup>
        <col className="ft-col-result" /><col className="ft-col-ticker" /><col className="ft-col-side" />
        <col className="ft-col-times" /><col className="ft-col-prices" /><col className="ft-col-pl" />
        <col className="ft-col-held" /><col className="ft-col-proof" />
      </colgroup>
      <thead>
        <tr>
          <th>Result</th><th>Ticker</th><th>Side</th><th>In → Out</th><th>Entry → Exit</th><th>{FT_PL_COLUMN}</th>
          <th>Held</th><th><span className="ft-sr">{FT_PROOF}</span></th>
        </tr>
      </thead>
      <tbody>
        {open.map((t) => <OpenRow key={t.id} t={t} onProof={onProof} compact={compact} isToday={isToday} />)}
        {shown.map((t) => (
          <tr key={t.id} className={`ft-closed ft-closed--${t.result ?? 'unscored'}`} data-testid={`ft-row-${t.id}`}>
            <td><ResultWord result={t.result} /></td>
            <td><Ticker symbol={t.symbol} className="ft-ticker" /><TickerMark ticker={t.ticker} /></td>
            <td><SideChip side={t.side} /></td>
            <td><TimeIn t={t} /> → <TimeOut t={t} /></td>
            <td><span className="ft-prices"><Entry t={t} compact={compact} /> → <Exit t={t} /></span></td>
            <td><PlCell trade={t} inline /></td>
            <td>{held(t.held)}</td>
            <td className="ft-right"><ProofLink t={t} onProof={onProof} /></td>
          </tr>
        ))}
        {folded > 0 && (
          <tr className="ft-fold-row">
            <td colSpan={8}>
              <button type="button" className="ft-link ft-fold" onClick={onShowAll} data-testid="ft-closed-earlier">
                +{folded} earlier closed trade{folded === 1 ? '' : 's'}
              </button>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
