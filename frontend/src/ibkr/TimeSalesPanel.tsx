/**
 * Live Time & Sales -- owns useIbkrTape (same pattern as DepthLadder → useIbkrDepth)
 * and renders the shared TimeSalesView. A capture replay reaches this same tape
 * line, so the badge, its tooltip and the empty message can be the replay's
 * (QA 2026-09-22, R16: a Session Record replay read LIVE).
 */
import { TimeSalesView } from './TimeSalesView';
import { useIbkrTape } from './useIbkrTape';

interface Props {
  symbol: string | null;
  /** Parent rail: pane chrome + LIVE; no duplicate outer card title. */
  embedded?: boolean;
  /** False on live-but-hidden trader tabs -- ring stays hot, UI does not. */
  uiActive?: boolean;
  /** Badge text while connected (default LIVE). */
  connectedText?: string;
  /** Badge tooltip. */
  statusTitle?: string;
  /** Empty-tape message while connected. */
  emptyLabel?: string;
}

export function TimeSalesPanel({
  symbol, embedded = false, uiActive = true, connectedText, statusTitle, emptyLabel,
}: Props) {
  const feed = useIbkrTape(symbol, uiActive);
  return (
    <TimeSalesView
      symbol={symbol}
      feed={feed}
      embedded={embedded}
      uiActive={uiActive}
      {...(connectedText !== undefined ? { connectedText } : {})}
      {...(statusTitle !== undefined ? { statusTitle } : {})}
      {...(emptyLabel !== undefined ? { emptyLabel } : {})}
    />
  );
}
