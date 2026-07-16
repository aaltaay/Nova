/**
 * DepthAndTape — Level 2 and Time & Sales side-by-side in one full-width row.
 * Composition only: each column is an independent module that owns its own feed.
 */
import { Level2Module, TimeSalesModule } from '../modules';

interface Props {
  symbol: string | null;
}

export function DepthAndTape({ symbol }: Props) {
  return (
    <div className="depth-and-tape">
      <div className="depth-and-tape__col">
        <Level2Module symbol={symbol} />
      </div>
      <div className="depth-and-tape__col">
        <TimeSalesModule symbol={symbol} />
      </div>
    </div>
  );
}
