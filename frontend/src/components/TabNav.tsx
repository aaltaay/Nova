/**
 * TabNav — renders the top tab-bar buttons for Nova.
 * Extracted from App.tsx to keep it under its 150-line target.
 * Tab row is tabs-only; scan age / data source live in AppHeader.
 */
export type ActiveTab = 'gappers' | 'movers' | 'afterhours' | 'catalysts' | 'hod_momo' | 'trading' | 'strategy' | 'reports';

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
}

export function TabNav({ activeTab, onTabClick, counts }: Props) {
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
        <button
          className={`tab ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => onTabClick('reports')}
        >
          Reports
        </button>
      </div>
    </div>
  );
}
