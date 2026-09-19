import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import { etTime, sourceLabel } from './historicalReplayFormat';

export function HistoricalQuoteTape({ data }: { data: HistoricalSnapshot }) {
  return <section className="sv-quote-depth-card" aria-label="Historical quote and tape" style={{ padding: 12, overflow: 'auto' }}>
    {data.error && <p role="alert">{data.error}</p>}
    <h3>{data.symbol} · Historical replay</h3>
    <p data-testid="historical-last">Last {data.last == null ? '—' : `$${data.last.toFixed(4)}`}</p>
    <p data-testid="historical-volume">Volume {data.volume?.toLocaleString() ?? '—'}</p>
    <p data-testid="historical-source">{sourceLabel(data)}</p>
    <p>Unreported prints are listed but excluded from candles, last and volume.</p>
    <p>Historical bid/ask and Level 2 unavailable</p>
    <h3>Time & Sales</h3>
    <table data-testid="historical-tape"><thead><tr><th>Time (ET)</th><th>Price</th><th>Size</th><th>Exchange</th><th>Note</th></tr></thead>
      <tbody>{data.prints.map((p, i) => <tr key={`${p.time}-${i}`}>
        <td>{etTime(p.time)}</td>
        <td>{p.price.toFixed(4)}</td><td>{p.size}</td><td>{p.exchange}</td>
        <td>{p.unreported ? 'Unreported' : ''}</td>
      </tr>)}</tbody></table>
    {!data.prints.length && <p>No reached trades in this replay window.</p>}
  </section>;
}
