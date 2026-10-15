/**
 * The nav rail's Bots group (operator decision 2026-10-15): Bots itself -- its page is empty for now -- with
 * LiveTrader Bots and Strategy Bots under it, laid out like the Scanner tree (children indented, icons only when
 * the rail is collapsed). Each child page has its family's key on top; the Bot switch itself is in the header.
 */
import {
  NAV_RAIL_LABEL_BOTS,
  NAV_RAIL_LABEL_BOTS_LIVE_TRADER,
  NAV_RAIL_LABEL_BOTS_STRATEGY,
  NAV_RAIL_TITLE_BOTS,
  NAV_RAIL_TITLE_BOTS_LIVE_TRADER,
  NAV_RAIL_TITLE_BOTS_STRATEGY,
} from '../constantGroups/nav_rail';
import { NavRailBotDot } from '../bot/NavRailBotDot';
import type { NavPage } from '../workspace/navRailStore';
import { navRailIcon } from './navRailIcons';
import { NavRailItem } from './NavRailItem';

interface Props {
  /** The shell page showing, or null while Trader is up. */
  page: NavPage | null;
  onOpen: (page: 'bots' | 'bots-live-trader' | 'bots-strategy') => void;
}

export function NavRailBotsTree({ page, onOpen }: Props) {
  const inGroup = page === 'bots' || page === 'bots-live-trader' || page === 'bots-strategy';
  return (
    <div className="nav-rail__tree nav-rail__tree--bots" data-testid="nav-rail-bots-tree">
      <div className="nav-rail__row">
        <NavRailItem
          testId="nav-rail-bots"
          className="nav-rail__section"
          icon={navRailIcon('bots')}
          label={NAV_RAIL_LABEL_BOTS}
          title={NAV_RAIL_TITLE_BOTS}
          active={inGroup}
          onClick={() => onOpen('bots')}
          trailing={<NavRailBotDot />}
        />
      </div>
      <NavRailItem
        testId="nav-rail-bots-live-trader"
        className="nav-rail__child"
        icon={navRailIcon('botsLiveTrader')}
        label={NAV_RAIL_LABEL_BOTS_LIVE_TRADER}
        title={NAV_RAIL_TITLE_BOTS_LIVE_TRADER}
        active={page === 'bots-live-trader'}
        onClick={() => onOpen('bots-live-trader')}
      />
      <NavRailItem
        testId="nav-rail-bots-strategy"
        className="nav-rail__child"
        icon={navRailIcon('botsStrategy')}
        label={NAV_RAIL_LABEL_BOTS_STRATEGY}
        title={NAV_RAIL_TITLE_BOTS_STRATEGY}
        active={page === 'bots-strategy'}
        onClick={() => onOpen('bots-strategy')}
      />
    </div>
  );
}
