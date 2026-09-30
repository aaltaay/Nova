/**
 * "Crypto -> stocks you can trade" (ADR 040): the stocks crypto moves, priced by IBKR, against what the coin's move
 * since the last 16:00 ET close implies for each. A symbol opens the Trader; every cell explains itself.
 */
import { pct, stockPrice, tone } from './format';
import { Card } from './parts';
import { phaseLabel, tipBeta, tipBridgeSymbol, tipClose, tipImplied, tipRead, tipSince } from './tips/glossaryDesk';
import { useTip } from './tips/TipHost';
import type { BridgeRow, CryptoBoard } from './types';

function readText(r: BridgeRow): string {
  if (r.read === null) return r.since_close_pct === null ? 'unknown' : '—';
  if (r.read === 'in_line') return 'in line';
  const gap = Math.abs(r.gap_pt ?? 0).toFixed(1);
  return r.read === 'ahead' ? `▲ ahead +${gap}` : `▼ behind −${gap}`;
}

export function BridgeCard({ board, onOpenTrader }: { board: CryptoBoard; onOpenTrader: (s: string) => void }) {
  const tip = useTip();
  const b = board.bridge;
  const move = (r: BridgeRow) => (r.driver === 'ETH' ? b.eth_since_close_pct : b.btc_since_close_pct);
  return (
    <Card
      title="Crypto → stocks you can trade"
      className="cx-bridge"
      testId="crypto-bridge"
      source={{ ids: ['ibkr', 'coinbase'], label: 'IBKR · live in Nova today', sources: board.sources, now: board.clock.now }}
    >
      <p className="cx-lede">
        Since the 16:00 ET close: BTC <strong className={tone(b.btc_since_close_pct)}>{pct(b.btc_since_close_pct)}</strong>
        {' · '}ETH <strong className={tone(b.eth_since_close_pct)}>{pct(b.eth_since_close_pct)}</strong>.
        {b.error ? <span className="cx-warn-inline"> {b.error}: stock prices unknown.</span> : ' These stocks open with it.'}
      </p>
      <table className="cx-table cx-table--tight">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>What it is</th>
            <th className="is-num">Close</th>
            <th className="is-num">{phaseLabel(b.phase)}</th>
            <th className="is-num">Implied</th>
            <th>Read</th>
          </tr>
        </thead>
        <tbody>
          {b.rows.map((r) => (
            <tr key={r.symbol} data-testid={`crypto-bridge-${r.symbol}`}>
              <td>
                <button type="button" className="cx-sym cx-sym--link" onClick={() => onOpenTrader(r.symbol)} {...tip(() => tipBridgeSymbol(r))}>
                  {r.symbol} <span className="cx-arrow">↗</span>
                </button>
              </td>
              <td className="cx-muted" {...tip(() => tipBeta(r))}>{r.what} · {r.beta === null ? '?' : `${r.beta.toFixed(1)}×`}</td>
              <td className="is-num" {...tip(() => tipClose(r, b.reference_close_at))}>{stockPrice(r.close)}</td>
              <td className={`is-num cx-strong ${r.since_close_pct === null ? 'cx-muted' : tone(r.since_close_pct)}`} {...tip(() => tipSince(r, b.phase))}>
                {r.since_close_pct === null ? (r.close === null ? '—' : 'No print yet') : pct(r.since_close_pct, 1)}
              </td>
              <td className={`is-num ${tone(r.implied_pct)}`} {...tip(() => tipImplied(r, move(r)))}>{pct(r.implied_pct, 1)}</td>
              <td {...tip(() => tipRead(r))}>
                <span className={`cx-read cx-read--${r.read ?? 'unknown'}`}>{readText(r)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="cx-warn">
        ⚠ In Nova, the ticker <strong>BTC</strong> is Grayscale&apos;s Bitcoin Mini Trust, a stock, not bitcoin.
        “Implied” is the move since the close × each stock&apos;s 60-day beta: a hint, never a price.
      </p>
    </Card>
  );
}
