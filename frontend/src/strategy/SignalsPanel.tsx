/** Signals panel — live feed of Gap and Go / Bull Flag / ABCD triggers from /ws/strategy. */
import { SETUP_LABELS } from '../constants';
import type { SetupSignal } from './types';

function fmtTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function fmtPrice(v: number | null): string {
  return v == null ? '—' : `$${v.toFixed(2)}`;
}

function SignalRow({
  signal,
  selected,
  onSelect,
}: {
  signal: SetupSignal;
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  return (
    <tr className={selected ? 'row-selected' : ''}>
      <td className="hod-time-cell">{fmtTime(signal.timestamp)}</td>
      <td>
        <button
          className={`symbol-btn${selected ? ' active' : ''}`}
          onClick={() => onSelect(signal.symbol)}
        >
          {signal.symbol}
        </button>
      </td>
      <td>
        <span className="pillar-chip pillar-pass">{SETUP_LABELS[signal.setup] ?? signal.setup}</span>
      </td>
      <td>{fmtPrice(signal.entry_price)}</td>
      <td>{fmtPrice(signal.stop_price)}</td>
      <td>{fmtPrice(signal.target_price)}</td>
      <td className="na-muted">{signal.notes[signal.notes.length - 1] ?? ''}</td>
    </tr>
  );
}

interface SignalsPanelProps {
  signals: SetupSignal[];
  connected: boolean;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

export function SignalsPanel({ signals, connected, selectedSymbol, onSelectSymbol }: SignalsPanelProps) {
  return (
    <div className="signals-panel">
      <div className="watchlist-description">
        Live setup triggers (Gap and Go, Bull Flag, ABCD) — signal only, no orders are placed.
        {!connected && <span className="na-muted"> Reconnecting…</span>}
      </div>
      {signals.length === 0 ? (
        <div className="empty-state">
          {connected ? 'Waiting for a setup to trigger…' : 'Connecting to the signal stream…'}
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Setup</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Target</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <SignalRow
                  key={`${s.symbol}-${s.setup}-${s.timestamp}-${i}`}
                  signal={s}
                  selected={selectedSymbol === s.symbol}
                  onSelect={onSelectSymbol}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
