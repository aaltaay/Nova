/**
 * Standalone Time & Sales module — mounts with only a symbol.
 * Owns its feed via TimeSalesPanel → useIbkrTape.
 */
import { TimeSalesPanel } from '../ibkr';

interface Props {
  symbol: string | null;
  /** Hide inner title when a parent pane already labels the module. */
  embedded?: boolean;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
  /** Badge text / tooltip / empty message -- a capture replay's instead of LIVE (R16). */
  connectedText?: string;
  statusTitle?: string;
  emptyLabel?: string;
  /** A Trader tab's Time & Sales: its line may be lent with the tab's Level 2 (ADR 043 decision 6). */
  traderTab?: boolean;
}

export function TimeSalesModule({
  symbol, embedded = false, uiActive = true, connectedText, statusTitle, emptyLabel, traderTab = false,
}: Props) {
  return (
    <div
      className="nova-module nova-module--time-sales"
      data-module="time-sales"
      data-symbol={symbol ?? ''}
    >
      <TimeSalesPanel
        key={symbol ?? 'none'}
        symbol={symbol}
        embedded={embedded}
        uiActive={uiActive}
        connectedText={connectedText}
        statusTitle={statusTitle}
        emptyLabel={emptyLabel}
        traderTab={traderTab}
      />
    </div>
  );
}
