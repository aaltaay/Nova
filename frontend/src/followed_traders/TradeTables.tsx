/**
 * A trader's trades, as the approved page drew them (2026-10-13, "E2"): each open position an OPEN tile, and the
 * closed trades a table striped by result. A time the feed did not see reads "by HH:MM:SS" (open when capture
 * started) or a window; an exit seen only in a window is IBKR's low–high, marked est.; a price Nova has not got says
 * why on hover. Closed rows drop to one line (`compact`) and their oldest fold into "+N earlier" when the page would
 * not fit otherwise. Nothing here places an order.
 */
import { tipProps } from '../ux/hoverTip';
import { FT_EST, FT_EST_TIP, FT_EXIT_PENDING, FT_NOW, FT_OPEN_CHIP, FT_PROOF } from './constants';
import { DASH, entered, etTime, exitPrice, exited, held, price } from './format';
import { PlCell, ResultWord, SideChip } from './parts';
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
  return (
    <span className={win ? 'ft-window' : undefined} {...tipProps(win ? 'The exit happened while the feed could not see the bar, somewhere in this window' : null)}>
      {exited(t.exit)}
    </span>
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

function ProofButton({ t, onProof }: { t: FollowedTrade; onProof: (id: string) => void }) {
  return (
    <button type="button" className="ft-link" onClick={() => onProof(t.id)} data-testid={`ft-proof-${t.id}`}
      aria-label={`${FT_PROOF}: ${t.trader} ${t.side} ${t.symbol}`}>
      {FT_PROOF}
    </button>
  );
}

/** One open position: what they hold, the price now and what it is worth per share, how long. */
export function OpenTile({ t, onProof }: { t: FollowedTrade; onProof: (id: string) => void }) {
  return (
    <div className="ft-tile" data-testid={`ft-row-${t.id}`}>
      <div className="ft-tile__row">
        <span className="ft-open-chip">{FT_OPEN_CHIP}</span>
        <span className="ft-tile__ticker">{t.symbol}</span>
        <SideChip side={t.side} />
        <span className="ft-tile__held ft-muted ft-xs">held {held(t.held)}</span>
      </div>
      <div className="ft-tile__row">
        <span className="ft-mono">{price(t.entry.avg_price)} → </span><Now t={t} />
        <span className="ft-muted ft-xs">{FT_NOW}</span>
        <span className="ft-tile__pl"><PlCell trade={t} inline big /></span>
      </div>
      <div className="ft-tile__row ft-xs">
        <span className="ft-muted">in <TimeIn t={t} /></span>
        {t.entry.first_price !== t.entry.avg_price && <span className="ft-note ft-note--warn">avg, was {price(t.entry.first_price)}</span>}
        <span className="ft-tile__proof"><ProofButton t={t} onProof={onProof} /></span>
      </div>
    </div>
  );
}

interface ClosedProps {
  trades: FollowedTrade[];
  onProof: (tradeId: string) => void;
  compact?: boolean;
  /** How many of the oldest are folded into "+N earlier". */
  folded?: number;
  onShowAll?: () => void;
}

export function ClosedTable({ trades, onProof, compact = false, folded = 0, onShowAll }: ClosedProps) {
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
          <th>Result</th><th>Ticker</th><th>Side</th><th>In → Out</th><th>Entry → Exit</th><th>P/L per share</th>
          <th>Held</th><th><span className="ft-sr">{FT_PROOF}</span></th>
        </tr>
      </thead>
      <tbody>
        {shown.map((t) => (
          <tr key={t.id} className={`ft-closed ft-closed--${t.result ?? 'unscored'}`} data-testid={`ft-row-${t.id}`}>
            <td><ResultWord result={t.result} /></td>
            <td className="ft-ticker">{t.symbol}</td>
            <td><SideChip side={t.side} /></td>
            <td><TimeIn t={t} /> → <TimeOut t={t} /></td>
            <td><span className="ft-prices"><Entry t={t} compact={compact} /> → <Exit t={t} /></span></td>
            <td><PlCell trade={t} inline /></td>
            <td>{held(t.held)}</td>
            <td className="ft-right"><ProofButton t={t} onProof={onProof} /></td>
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
