/**
 * HOD / Running Up pills plus optional IBKR roster scanner pills.
 */
import {
  SCANNER_DOCK_ALERT_MODES,
  SCANNER_DOCK_MODE_LABEL,
  SCANNER_DOCK_MODE_TESTID,
  SCANNER_DOCK_MODE_TITLE,
  SCANNER_DOCK_ROSTER_MODES,
  type HodDockMode,
  type ScannerDockRosterMode,
} from './scannerDockModes';

function formatCount(n: number): string {
  if (n <= 0) return '';
  if (n > 99) return '99+';
  return String(n);
}

function ModePill({
  mode,
  active,
  count,
  onSelect,
}: {
  mode: HodDockMode;
  active: boolean;
  count: number;
  onSelect: (mode: HodDockMode) => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={active ? 'hod-momo-dock__mode is-active' : 'hod-momo-dock__mode'}
      data-testid={SCANNER_DOCK_MODE_TESTID[mode]}
      title={SCANNER_DOCK_MODE_TITLE[mode]}
      onClick={() => onSelect(mode)}
    >
      {SCANNER_DOCK_MODE_LABEL[mode]}
      {count > 0 ? (
        <span className="hod-momo-dock__count">{formatCount(count)}</span>
      ) : null}
    </button>
  );
}

type Props = {
  dockMode: HodDockMode;
  onSelect: (mode: HodDockMode) => void;
  hodCount: number;
  runningUpCount: number;
  rosterCounts?: Record<ScannerDockRosterMode, number> | null;
};

export function HodMomoDockModes({
  dockMode,
  onSelect,
  hodCount,
  runningUpCount,
  rosterCounts,
}: Props) {
  const alertCount: Record<(typeof SCANNER_DOCK_ALERT_MODES)[number], number> = {
    hod_momo: hodCount,
    running_up: runningUpCount,
  };

  return (
    <div
      className="hod-momo-dock__modes"
      role="tablist"
      aria-label="Scanner dock mode"
      onClick={(e) => e.stopPropagation()}
    >
      {SCANNER_DOCK_ALERT_MODES.map((mode) => (
        <ModePill
          key={mode}
          mode={mode}
          active={dockMode === mode}
          count={alertCount[mode]}
          onSelect={onSelect}
        />
      ))}
      {rosterCounts ? (
        <>
          <span className="hod-momo-dock__mode-gap" aria-hidden="true" />
          {SCANNER_DOCK_ROSTER_MODES.map((mode) => (
            <ModePill
              key={mode}
              mode={mode}
              active={dockMode === mode}
              count={rosterCounts[mode]}
              onSelect={onSelect}
            />
          ))}
        </>
      ) : null}
    </div>
  );
}
