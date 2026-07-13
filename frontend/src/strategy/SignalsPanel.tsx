/** Signals panel — live feed of Gap and Go / Bull Flag / ABCD triggers from /ws/strategy. */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
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
  onOpenTrading,
}: {
  signal: SetupSignal;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  return (
    <SelectableTableRow
      symbol={signal.symbol}
      selected={selected}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
    >
      <td className="hod-time-cell">{fmtTime(signal.timestamp)}</td>
      <td>
        <SymbolSelectButton
          symbol={signal.symbol}
          selected={selected}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />
      </td>
      <td>
        <span className="pillar-chip pillar-pass">{SETUP_LABELS[signal.setup] ?? signal.setup}</span>
      </td>
      <td>{fmtPrice(signal.entry_price)}</td>
      <td>{fmtPrice(signal.stop_price)}</td>
      <td>{fmtPrice(signal.target_price)}</td>
      <td className="na-muted">{signal.notes[signal.notes.length - 1] ?? ''}</td>
    </SelectableTableRow>
  );
}

interface SignalsPanelProps {
  signals: SetupSignal[];
  connected: boolean;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function SignalsPanel({
  signals, connected, selectedSymbol, onSelectSymbol, onOpenTrading,
}: SignalsPanelProps) {
  return (
    <div className="signals-panel">
      <div className="watchlist-description">
        Live setup triggers (Gap and Go, Bull Flag, ABCD) — signal only, no orders are placed.
        Click a symbol for the side panel; double-click for the full trading view.
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
                <th title="When this setup was detected as eligible.">Time</th>
                <th title="Click: side panel. Double-click: full trading view.">Symbol</th>
                <th title="Which pattern triggered: Gap and Go, Bull Flag, or ABCD. See backend/strategy/*.py for the exact rule.">Setup</th>
                <th title="Suggested entry price if this signal were acted on.">Entry</th>
                <th title="Suggested stop-loss price if this signal were acted on.">Stop</th>
                <th title="Suggested target price if this signal were acted on.">Target</th>
                <th title="The setup module's own explanation of why it triggered (or didn't fully qualify).">Detail</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <SignalRow
                  key={`${s.symbol}-${s.setup}-${s.timestamp}-${i}`}
                  signal={s}
                  selected={selectedSymbol === s.symbol}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
