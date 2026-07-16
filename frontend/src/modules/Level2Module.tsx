/**
 * Standalone Level 2 module — mounts with only a symbol.
 * Owns its feed via DepthLadder → useIbkrDepth.
 */
import { DepthLadder } from '../ibkr';

interface Props {
  symbol: string | null;
}

export function Level2Module({ symbol }: Props) {
  return (
    <div
      className="nova-module nova-module--level2"
      data-module="level2"
      data-symbol={symbol ?? ''}
    >
      <DepthLadder key={symbol ?? 'none'} symbol={symbol} />
    </div>
  );
}
