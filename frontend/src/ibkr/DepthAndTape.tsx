/**
 * DepthAndTape — Level 2 and Time & Sales side-by-side in one full-width row.
 */
import { DepthLadder } from './DepthLadder';
import { TimeSalesPanel } from './TimeSalesPanel';
import { useIbkrTape } from './useIbkrTape';

interface Props {
  symbol: string | null;
}

export function DepthAndTape({ symbol }: Props) {
  const tape = useIbkrTape(symbol);

  return (
    <div className="depth-and-tape">
      <div className="depth-and-tape__col">
        <DepthLadder key={symbol ?? 'none'} symbol={symbol} />
      </div>
      <div className="depth-and-tape__col">
        <TimeSalesPanel
          prints={tape.prints}
          connected={tape.connected}
          error={tape.error}
        />
      </div>
    </div>
  );
}
