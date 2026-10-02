/**
 * Live Time & Sales -- owns useIbkrTape (same pattern as DepthLadder → useIbkrDepth)
 * and renders the shared TimeSalesView. A capture replay reaches this same tape
 * line, so the badge, its tooltip and the empty message can be the replay's
 * (QA 2026-09-22, R16: a Session Record replay read LIVE).
 *
 * On the live tape the badge says when IBKR data stopped arriving on every line
 * (NO DATA 9s) or did a moment ago (DATA GAP 16s), with the reason on hover (#672):
 * on 2026-10-01 this tape froze for 16 s under a LIVE badge while the Wi-Fi reconnected.
 *
 * A Trader tab's Time & Sales (`traderTab`) may lend its line with the tab's Level 2 while the
 * tab is hidden (ADR 043 decision 6); it then reads LENT and says whose setup took it.
 */
import { useFeedGapBadge } from './feedPulseStore';
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
  /** A Trader tab's Time & Sales: its line may be lent while the tab is hidden (ADR 043 decision 6). */
  traderTab?: boolean;
}

export function TimeSalesPanel({
  symbol, embedded = false, uiActive = true, connectedText, statusTitle, emptyLabel, traderTab = false,
}: Props) {
  const feed = useIbkrTape(symbol, uiActive, { traderTab });
  const gap = useFeedGapBadge();
  // A caller's own badge (a capture replay) is not the live feed's.
  const live = connectedText === undefined && gap != null;
  return (
    <TimeSalesView
      symbol={symbol}
      feed={feed}
      embedded={embedded}
      uiActive={uiActive}
      {...(live ? { connectedText: gap.label, statusTitle: gap.title, statusTone: gap.tone } : {})}
      {...(connectedText !== undefined ? { connectedText } : {})}
      {...(statusTitle !== undefined ? { statusTitle } : {})}
      {...(emptyLabel !== undefined ? { emptyLabel } : {})}
    />
  );
}
