/**
 * Standalone Level 2 module — mounts with only a symbol.
 * Owns its feed via DepthLadder → useIbkrDepth.
 */
import { DepthLadder } from '../ibkr';

interface Props {
  symbol: string | null;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
}

export function Level2Module({ symbol, uiActive = true }: Props) {
  return (
    <div
      className="nova-module nova-module--level2"
      data-module="level2"
      data-symbol={symbol ?? ''}
    >
      <DepthLadder key={symbol ?? 'none'} symbol={symbol} uiActive={uiActive} />
    </div>
  );
}
