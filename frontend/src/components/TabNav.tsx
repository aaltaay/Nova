/**
 * TabNav — renders the top tab-bar buttons for Nova.
 * Extracted from App.tsx to keep it under its 150-line target.
 * All existing CSS classes are preserved exactly.
 */
import { CATALYSTS_EXPERIMENTAL_LABEL } from '../constants';

export type ActiveTab = 'gappers' | 'movers' | 'afterhours' | 'catalysts' | 'hod_momo' | 'trading' | 'strategy';

interface Props {
  activeTab: ActiveTab;
  onTabClick: (tab: ActiveTab) => void;
  counts: {
    gappers: number;
    movers: number;
    afterhours: number;
    catalysts: number;
    hodMomo: number;
    watchlist: number;
  };
  secondsAgo: number | null;
  historyDate: string | null;
}

export function TabNav({ activeTab, onTabClick, counts, secondsAgo, historyDate }: Props) {
  return (
    <div className="tab-bar">
      <div className="tab-bar-scroll">
        <button
          className={`tab ${activeTab === 'gappers' ? 'active' : ''}`}
          onClick={() => onTabClick('gappers')}
        >
          Gappers
          {counts.gappers > 0 && <span className="tab-count">{counts.gappers}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'movers' ? 'active' : ''}`}
          onClick={() => onTabClick('movers')}
        >
          Movers
          {counts.movers > 0 && <span className="tab-count">{counts.movers}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'afterhours' ? 'active' : ''}`}
          onClick={() => onTabClick('afterhours')}
        >
          After Hours
          {counts.afterhours > 0 && <span className="tab-count">{counts.afterhours}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'catalysts' ? 'active' : ''}`}
          onClick={() => onTabClick('catalysts')}
        >
          Catalysts
          <span className="tab-badge-experimental">{CATALYSTS_EXPERIMENTAL_LABEL}</span>
          {counts.catalysts > 0 && <span className="tab-count">{counts.catalysts}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'hod_momo' ? 'active' : ''}`}
          onClick={() => onTabClick('hod_momo')}
        >
          HOD Momo
          {counts.hodMomo > 0 && <span className="tab-count">{counts.hodMomo}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'trading' ? 'active' : ''}`}
          onClick={() => onTabClick('trading')}
        >
          Trading
          <span className="tab-badge-broker">IBKR</span>
        </button>
        <button
          className={`tab ${activeTab === 'strategy' ? 'active' : ''}`}
          onClick={() => onTabClick('strategy')}
        >
          Watchlist
          {counts.watchlist > 0 && <span className="tab-count">{counts.watchlist}</span>}
        </button>
      </div>
      {!historyDate && secondsAgo != null && (
        <span className="scan-age tab-bar-meta">updated {secondsAgo}s ago</span>
      )}
      <span
        className="tab-data-source-badge"
        title="Scanner data provided by Alpaca Markets (free IEX or SIP feed)"
      >
        {activeTab !== 'trading' ? 'Data: Alpaca' : ''}
      </span>
    </div>
  );
}
