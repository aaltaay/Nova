/**
 * Live Time & Sales -- owns useIbkrTape (same pattern as DepthLadder → useIbkrDepth)
 * and renders the shared TimeSalesView.
 */
import { TimeSalesView } from './TimeSalesView';
import { useIbkrTape } from './useIbkrTape';

interface Props {
  symbol: string | null;
  /** Parent rail: pane chrome + LIVE; no duplicate outer card title. */
  embedded?: boolean;
  /** False on live-but-hidden trader tabs -- ring stays hot, UI does not. */
  uiActive?: boolean;
}

export function TimeSalesPanel({ symbol, embedded = false, uiActive = true }: Props) {
  const feed = useIbkrTape(symbol, uiActive);
  return <TimeSalesView symbol={symbol} feed={feed} embedded={embedded} uiActive={uiActive} />;
}
