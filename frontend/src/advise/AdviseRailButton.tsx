/**
 * Advise entry on the nav rail foot (above Settings). Renders nothing without
 * an AdviseProvider so the sample desk and tests never show a dead door.
 */
import { scannerNavIcon } from '../scanner/scannerNavIcons';
import { ADVISE_RAIL_LABEL } from './constants';
import { useAdviseOptional } from './AdviseContext';

export function AdviseRailButton() {
  const advise = useAdviseOptional();
  if (!advise) return null;
  return (
    <button
      type="button"
      className={`nav-rail__item${advise.open ? ' is-active' : ''}`}
      data-testid="nav-rail-advise"
      title={ADVISE_RAIL_LABEL}
      onClick={advise.openAdvise}
    >
      {scannerNavIcon('advise')}
      <span className="nav-rail__txt">{ADVISE_RAIL_LABEL}</span>
    </button>
  );
}
