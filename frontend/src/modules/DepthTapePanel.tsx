/** Level 2 + Time & Sales section — gates on workspace IBKR connection + symbol match. */
import { DepthAndTape } from '../ibkr/DepthAndTape';
import { TICKER_L2_SOURCE_LABEL, TICKER_TRADE_DEPTH_LEVELS } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';

interface Props {
  /** Panel selection source of truth (never a stale detail.symbol). */
  selectedSymbol: string;
  detailSymbol: string;
}

export function DepthTapePanel({ selectedSymbol, detailSymbol }: Props) {
  const { ibkrConnected } = useWorkspace();
  const depthSymbol = selectedSymbol.toUpperCase();
  const detailMatchesSelection = detailSymbol.toUpperCase() === depthSymbol;

  if (!ibkrConnected || !detailMatchesSelection) return null;

  return (
    <div
      className="nova-module nova-module--depth-tape cq-depth-stack"
      data-module="depth-tape"
      data-symbol={depthSymbol}
    >
      <div className="cq-section-title">
        Level 2{' '}
        <span className="na-muted">
          (top {TICKER_TRADE_DEPTH_LEVELS} · {TICKER_L2_SOURCE_LABEL})
        </span>
      </div>
      <DepthAndTape key={depthSymbol} symbol={depthSymbol} />
    </div>
  );
}
