import {
  RecentDecisionsTable,
  SnapsTable,
} from './HodMomoDebugTables';
import { CountersCard } from './HodMomoDebugCounters';
import { SymbolInspector } from './HodMomoSymbolInspector';
import { useHodMomoDebugPoll } from './useHodMomoDebugPoll';
import { useState } from 'react';

interface HodMomoDebugPanelProps {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function HodMomoDebugPanel({
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: HodMomoDebugPanelProps) {
  const { counters, countersAge, decisions, snaps } = useHodMomoDebugPoll();
  const [activeSection, setActiveSection] = useState<'counters' | 'decisions' | 'snaps' | 'inspector'>('counters');

  return (
    <div className="dbg-panel">
      <div className="dbg-nav">
        {(['counters', 'decisions', 'snaps', 'inspector'] as const).map(s => (
          <button
            key={s}
            className={`dbg-nav-btn${activeSection === s ? ' active' : ''}`}
            onClick={() => setActiveSection(s)}
          >
            {s === 'counters' ? '📊 Counters' :
             s === 'decisions' ? '🔍 Decisions' :
             s === 'snaps' ? '📷 Snaps' : '🔎 Inspector'}
          </button>
        ))}
      </div>

      <div className="dbg-content">
        {activeSection === 'counters' && (
          <CountersCard data={counters} age={countersAge} />
        )}
        {activeSection === 'decisions' && (
          <RecentDecisionsTable
            decisions={decisions}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={onSelectSymbol}
            onOpenTrading={onOpenTrading}
          />
        )}
        {activeSection === 'snaps' && (
          <SnapsTable
            snaps={snaps}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={onSelectSymbol}
            onOpenTrading={onOpenTrading}
          />
        )}
        {activeSection === 'inspector' && (
          <SymbolInspector />
        )}
      </div>
    </div>
  );
}
