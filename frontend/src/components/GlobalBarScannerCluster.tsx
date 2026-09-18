import { SymbolSearchBox } from './SymbolSearchBox';
import { EmergencyKillButton } from './EmergencyKillButton';
import { fmtHistoryDateShort, type GlobalAppBarScanner } from './globalAppBarScanner';

export function GlobalBarScannerCluster({ scanner }: { scanner: GlobalAppBarScanner }) {
  return (
    <div
      className="global-app-bar__context global-app-bar__scanner"
      data-testid="global-bar-scanner"
    >
      {scanner.onSampleDataToggle && (
        <label
          className={`sample-data-switch${scanner.sampleDataActive ? ' sample-data-switch--on' : ''}`}
          title="Open isolated sample fixtures — never mixed with live market data"
          data-testid="sample-data-switch"
        >
          <input
            type="checkbox"
            checked={scanner.sampleDataActive}
            onChange={(e) => scanner.onSampleDataToggle?.(e.target.checked)}
          />
          <span>Sample</span>
        </label>
      )}
      <select
        className={`history-select${scanner.historyDate ? ' history-select--active' : ''}`}
        value={scanner.historyDate ?? ''}
        onChange={scanner.onHistoryChange}
        title="Browse historical snapshots"
        disabled={scanner.sampleDataActive}
      >
        <option value="">{scanner.sampleDataActive ? 'Sample (fixtures)' : 'Today (Live)'}</option>
        {!scanner.sampleDataActive &&
          scanner.historyDates.map((d) => (
            <option key={d} value={d}>
              {fmtHistoryDateShort(d)}
            </option>
          ))}
      </select>
      <SymbolSearchBox onLookup={scanner.onLookup} />
      <EmergencyKillButton />
    </div>
  );
}
