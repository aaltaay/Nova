/**
 * Stock View Level 2 + Time & Sales — side-by-side in one module card.
 * Matched pane headers (no duplicate outer "Level 2 · Time & Sales" title).
 * Height vs Order Entry is controlled by StockViewRail's horizontal splitter.
 */
import { Level2Module } from '../modules/Level2Module';
import { TimeSalesModule } from '../modules/TimeSalesModule';
import {
  STOCK_VIEW_MODULE_DEPTH_TITLE,
  STOCK_VIEW_MODULE_L2_TITLE,
} from '../constants';
import { useModuleVisibility, useWorkspace } from '../workspace';
import { StockViewModuleCard } from './StockViewModuleCard';

interface Props {
  selectedSymbol: string;
  detailSymbol: string;
}

export function StockViewDepthTape({ selectedSymbol, detailSymbol }: Props) {
  const { ibkrConnected } = useWorkspace();
  const { isVisible } = useModuleVisibility();
  const depthSymbol = selectedSymbol.toUpperCase();
  const detailMatches = detailSymbol.toUpperCase() === depthSymbol;
  const showL2 = isVisible('level2');
  const showTape = isVisible('tape');

  if (!ibkrConnected || !detailMatches) {
    return (
      <StockViewModuleCard
        title={STOCK_VIEW_MODULE_DEPTH_TITLE}
        className="sv-depth-card sv-depth-card--empty"
        testId="stock-view-depth-stack"
      >
        <p className="sv-depth-stack__hint">Connect IB Gateway for Level 2 and Time & Sales</p>
      </StockViewModuleCard>
    );
  }

  if (!showL2 && !showTape) return null;

  return (
    <StockViewModuleCard
      className="sv-depth-card"
      testId="stock-view-depth-stack"
      aria-label={STOCK_VIEW_MODULE_DEPTH_TITLE}
    >
      <div
        className="depth-and-tape sv-depth-and-tape"
        data-module="stock-view-depth"
        data-symbol={depthSymbol}
        data-testid="stock-view-depth-side-by-side"
      >
        {showL2 && (
          <div className="depth-and-tape__col sv-depth-and-tape__l2" data-testid="stock-view-l2-col">
            <div className="sv-md-pane">
              <div className="sv-md-pane__head">
                <h3 className="sv-md-pane__title">{STOCK_VIEW_MODULE_L2_TITLE}</h3>
              </div>
              <div className="sv-md-pane__body">
                <Level2Module symbol={depthSymbol} />
              </div>
            </div>
          </div>
        )}
        {showTape && (
          <div className="depth-and-tape__col sv-depth-and-tape__tape" data-testid="stock-view-tape-col">
            <TimeSalesModule symbol={depthSymbol} embedded />
          </div>
        )}
      </div>
    </StockViewModuleCard>
  );
}
