/**
 * Standalone Level 2 module — mounts with only a symbol.
 * Owns its feed via DepthLadder → useIbkrDepth.
 */
import { DepthLadder, type DepthMarker } from '../ibkr';

interface Props {
  symbol: string | null;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
  /** The plan's ENTRY / STOP / TARGET in the book (ADR 037). */
  markers?: readonly DepthMarker[];
}

export function Level2Module({ symbol, uiActive = true, markers }: Props) {
  return (
    <div
      className="nova-module nova-module--level2"
      data-module="level2"
      data-symbol={symbol ?? ''}
    >
      <DepthLadder key={symbol ?? 'none'} symbol={symbol} uiActive={uiActive} markers={markers} />
    </div>
  );
}
