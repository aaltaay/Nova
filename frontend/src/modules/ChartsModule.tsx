/**
 * Charts module — thin registry wrapper around the panel chart.
 * Full Stock View grid stays on StockViewPage; this is the side-panel chart.
 */
import { TickerChart } from '../TickerChart';

interface Props {
  symbol?: string | null;
}

export function ChartsModule({ symbol }: Props) {
  const sym = (symbol ?? '').trim().toUpperCase();
  return (
    <div className="nova-module nova-module--charts" data-module="charts" data-symbol={sym}>
      {sym ? <TickerChart symbol={sym} variant="panel" /> : null}
    </div>
  );
}
