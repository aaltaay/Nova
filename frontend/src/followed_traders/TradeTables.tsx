/**
 * A trader's Holding now and Closed tables, as the design drew them. A time the feed did not see reads "by
 * HH:MM:SS" (open when capture started) or a window; an exit seen only in a window is IBKR's low–high, marked est.;
 * a price Nova has not got says why on hover. Nothing here places an order.
 */
import { tipProps } from '../ux/hoverTip';
import { FT_EST, FT_EST_TIP, FT_EXIT_PENDING, FT_PROOF } from './constants';
import { DASH, entered, etTime, exitPrice, exited, held, price } from './format';
import { PlCell, ResultChip, SideChip } from './parts';
import type { FollowedTrade } from './types';

interface TableProps {
  trades: FollowedTrade[];
  onProof: (tradeId: string) => void;
}

function EntryCell({ t }: { t: FollowedTrade }) {
  const added = t.entry.first_price !== t.entry.avg_price;
  return (
    <span className="ft-stack">
      <span className="ft-mono ft-strong-num">{price(t.entry.avg_price)}</span>
      {added && <span className="ft-note ft-note--warn">avg · added, was {price(t.entry.first_price)}</span>}
    </span>
  );
}

function TimeIn({ t }: { t: FollowedTrade }) {
  const unseen = !t.entry.known || t.entry.since_ts !== null;
  const tip = !t.entry.known ? 'Already open when capture started: its real entry time is unknown' :
    t.entry.since_ts !== null ? 'The entry happened while the feed could not see the bar, somewhere in this window' : null;
  return <span className={unseen ? 'ft-muted ft-unseen' : undefined} {...tipProps(tip)}>{entered(t.entry)}</span>;
}

function NowCell({ t }: { t: FollowedTrade }) {
  const now = t.now;
  if (now?.state === 'live') return <span className="ft-mono">{price(now.price)}</span>;
  const why = now?.why ?? (now?.state === 'waiting' ? 'opening IBKR’s line' : null);
  return <span className="ft-mono ft-muted" {...tipProps(why)}>{now?.state === 'waiting' ? '…' : DASH}</span>;
}

function ExitCell({ t }: { t: FollowedTrade }) {
  const exit = t.exit;
  if (!exit) return <span className="ft-muted">{DASH}</span>;
  if (exit.state === 'range') {
    return (
      <span className="ft-mono" {...tipProps(FT_EST_TIP)}>
        {exitPrice(exit)} <span className="ft-est">{FT_EST}</span>
      </span>
    );
  }
  const muted = exit.state !== 'at';
  const tip = exit.state === 'at' && exit.trade_ts ? `IBKR’s last trade by the exit, printed ${etTime(exit.trade_ts)} ET` : exit.why;
  return <span className={`ft-mono${muted ? ' ft-muted' : ''}`} {...tipProps(tip)}>{exit.state === 'pending' && !exit.why ? FT_EXIT_PENDING : exitPrice(exit)}</span>;
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

function ProofButton({ t, onProof }: { t: FollowedTrade; onProof: (id: string) => void }) {
  return (
    <button type="button" className="ft-link" onClick={() => onProof(t.id)} data-testid={`ft-proof-${t.id}`}
      aria-label={`${FT_PROOF}: ${t.trader} ${t.side} ${t.symbol}`}>
      {FT_PROOF}
    </button>
  );
}

export function HoldingTable({ trades, onProof }: TableProps) {
  return (
    <div className="ft-table-scroll">
      <table className="ft-table ft-table--holding">
        <thead>
          <tr>
            <th>Time in</th><th>Ticker</th><th>Side</th><th>Entry</th><th>Now</th><th>Unrl P/L</th><th>Held</th>
            <th className="ft-right"><span className="ft-sr">Proof</span></th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="ft-row--holding" data-testid={`ft-row-${t.id}`}>
              <td><TimeIn t={t} /></td>
              <td className="ft-ticker ft-ticker--big">{t.symbol}</td>
              <td><SideChip side={t.side} /></td>
              <td><EntryCell t={t} /></td>
              <td><NowCell t={t} /></td>
              <td><PlCell trade={t} /></td>
              <td>{held(t.held)}</td>
              <td className="ft-right"><ProofButton t={t} onProof={onProof} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ClosedTable({ trades, onProof }: TableProps) {
  return (
    <div className="ft-table-scroll">
      <table className="ft-table ft-table--closed">
        <thead>
          <tr>
            <th>Time in</th><th>Time out</th><th>Ticker</th><th>Side</th><th>Entry</th><th>Exit</th><th>P/L</th>
            <th>Held</th><th className="ft-right"><span className="ft-sr">Proof</span></th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} data-testid={`ft-row-${t.id}`}>
              <td><TimeIn t={t} /></td>
              <td><TimeOut t={t} /></td>
              <td className="ft-ticker">{t.symbol}</td>
              <td><SideChip side={t.side} /></td>
              <td><EntryCell t={t} /></td>
              <td><ExitCell t={t} /></td>
              <td><span className="ft-pl-result"><PlCell trade={t} /><ResultChip result={t.result} /></span></td>
              <td>{held(t.held)}</td>
              <td className="ft-right"><ProofButton t={t} onProof={onProof} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
