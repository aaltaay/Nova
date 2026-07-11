import { useIbkrDepth } from './useIbkrDepth';
import type { DepthLevel } from './types';

interface Props {
  symbol: string | null;
}

function fmtPrice(p: number | null | undefined) {
  if (p == null) return '—';
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function fmtSize(s: number | null | undefined) {
  if (s == null) return '—';
  return s.toLocaleString('en-US');
}

function LevelRow({ level, side }: { level: DepthLevel; side: 'bid' | 'ask' }) {
  const isAsk = side === 'ask';
  return (
    <tr className={`ibkr-depth-row ibkr-depth-${side}`}>
      {isAsk ? (
        <>
          <td className="ibkr-depth-size">{fmtSize(level.size)}</td>
          <td className="ibkr-depth-price ibkr-ask-price">{fmtPrice(level.price)}</td>
        </>
      ) : (
        <>
          <td className="ibkr-depth-price ibkr-bid-price">{fmtPrice(level.price)}</td>
          <td className="ibkr-depth-size">{fmtSize(level.size)}</td>
        </>
      )}
    </tr>
  );
}

export function DepthLadder({ symbol }: Props) {
  const { book, connected, l1Fallback } = useIbkrDepth(symbol);

  if (!symbol) {
    return <div className="ibkr-depth-empty">Enter a symbol to view the order book.</div>;
  }

  if (!connected || !book) {
    return (
      <div className="ibkr-depth-empty">
        {connected ? 'Waiting for book data…' : `Connecting depth for ${symbol}…`}
      </div>
    );
  }

  return (
    <div className="ibkr-depth-ladder">
      {l1Fallback && (
        <div className="ibkr-depth-fallback-badge">
          Level 1 only — depth entitlement pending
        </div>
      )}
      <table className="ibkr-depth-table">
        <thead>
          <tr>
            <th>Bid</th>
            <th>Ask Size</th>
          </tr>
          <tr>
            <th>Price</th>
            <th>Size</th>
          </tr>
        </thead>
        <tbody>
          {/* Asks displayed top-to-bottom (ascending price, closest ask first) */}
          {[...book.asks].reverse().map((level, i) => (
            <LevelRow key={`ask-${i}`} level={level} side="ask" />
          ))}
          {/* Spread indicator */}
          {book.bids[0] && book.asks[0] && (
            <tr className="ibkr-depth-spread">
              <td colSpan={2} style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                spread {fmtPrice(Math.abs(book.asks[0].price - book.bids[0].price))}
              </td>
            </tr>
          )}
          {/* Bids displayed top-to-bottom (descending price, best bid first) */}
          {book.bids.map((level, i) => (
            <LevelRow key={`bid-${i}`} level={level} side="bid" />
          ))}
        </tbody>
      </table>
    </div>
  );
}
