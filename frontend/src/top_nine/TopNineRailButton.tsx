/**
 * The grid button beside Gappers, Gainers and After Hours on the rail (where the operator drew it,
 * 2026-10-26): opens the Top 9 pop-up on that list, or switches the open one to it.
 */
import { useState } from 'react';
import { TOP_NINE_OPEN_TITLE, type TopNineList } from './topNineConstants';
import { GridIcon } from './TopNineIcons';
import { openTopNineWindow } from './topNineNav';
import './topNineRail.css';

const BLOCKED_WHY = 'The browser blocked the pop-up window. Allow pop-ups for Nova, then press again.';

export function TopNineRailButton({ list, label }: { list: TopNineList; label: string }) {
  const [blocked, setBlocked] = useState(false);
  return (
    <button
      type="button"
      className={`top-nine-rail-btn${blocked ? ' is-blocked' : ''}`}
      data-testid={`nav-rail-top-nine-${list}`}
      aria-label={`${label}: Top 9`}
      title={blocked ? BLOCKED_WHY : TOP_NINE_OPEN_TITLE(label)}
      onClick={() => {
        void openTopNineWindow(list).then((opened) => setBlocked(!opened));
      }}
    >
      <GridIcon size={12} />
    </button>
  );
}
