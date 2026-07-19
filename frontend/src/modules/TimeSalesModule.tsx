/**
 * Standalone Time & Sales module — mounts with only a symbol.
 * Owns its feed via TimeSalesPanel → useIbkrTape.
 */
import { TimeSalesPanel } from '../ibkr';

interface Props {
  symbol: string | null;
  /** Hide inner title when a parent pane already labels the module. */
  embedded?: boolean;
}

export function TimeSalesModule({ symbol, embedded = false }: Props) {
  return (
    <div
      className="nova-module nova-module--time-sales"
      data-module="time-sales"
      data-symbol={symbol ?? ''}
    >
      <TimeSalesPanel key={symbol ?? 'none'} symbol={symbol} embedded={embedded} />
    </div>
  );
}
