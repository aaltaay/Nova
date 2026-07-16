/** Level 2 + Time & Sales — respects module visibility (Phase 4). */
import { Level2Module } from './Level2Module';
import { TimeSalesModule } from './TimeSalesModule';
import { TICKER_L2_SOURCE_LABEL, TICKER_TRADE_DEPTH_LEVELS } from '../constants';
import { useModuleVisibility, useWorkspace } from '../workspace';

interface Props {
  /** Panel selection source of truth (never a stale detail.symbol). */
  selectedSymbol: string;
  detailSymbol: string;
}

export function DepthTapePanel({ selectedSymbol, detailSymbol }: Props) {
  const { ibkrConnected } = useWorkspace();
  const { isVisible } = useModuleVisibility();
  const depthSymbol = selectedSymbol.toUpperCase();
  const detailMatchesSelection = detailSymbol.toUpperCase() === depthSymbol;
  const showL2 = isVisible('level2');
  const showTape = isVisible('tape');

  if (!ibkrConnected || !detailMatchesSelection) return null;
  if (!showL2 && !showTape) return null;

  return (
    <div
      className="nova-module nova-module--depth-tape cq-depth-stack"
      data-module="depth-tape"
      data-symbol={depthSymbol}
    >
      {showL2 && (
        <div className="cq-section-title">
          Level 2{' '}
          <span className="na-muted">
            (top {TICKER_TRADE_DEPTH_LEVELS} · {TICKER_L2_SOURCE_LABEL})
          </span>
        </div>
      )}
      <div className="depth-and-tape">
        {showL2 && (
          <div className="depth-and-tape__col">
            <Level2Module symbol={depthSymbol} />
          </div>
        )}
        {showTape && (
          <div className="depth-and-tape__col">
            <TimeSalesModule symbol={depthSymbol} />
          </div>
        )}
      </div>
    </div>
  );
}
