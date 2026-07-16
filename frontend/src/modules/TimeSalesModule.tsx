/**
 * Standalone Time & Sales module — mounts with only a symbol.
 * Owns its feed via TimeSalesPanel → useIbkrTape.
 */
import { TimeSalesPanel } from '../ibkr/TimeSalesPanel';

interface Props {
  symbol: string | null;
}

export function TimeSalesModule({ symbol }: Props) {
  return (
    <div
      className="nova-module nova-module--time-sales"
      data-module="time-sales"
      data-symbol={symbol ?? ''}
    >
      <TimeSalesPanel key={symbol ?? 'none'} symbol={symbol} />
    </div>
  );
}
