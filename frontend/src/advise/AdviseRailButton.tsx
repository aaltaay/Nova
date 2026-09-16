import { scannerNavIcon } from '../scanner/scannerNavIcons';
import { ADVISE_RAIL_LABEL } from './constants';
import { useAdviseOptional } from './AdviseContext';

export function AdviseRailButton() {
  const advise = useAdviseOptional();
  if (!advise) return null;
  return (
    <button
      type="button"
      className={`scanner-side-nav__item${advise.open ? ' is-active' : ''}`}
      data-testid="scanner-nav-advise"
      title={ADVISE_RAIL_LABEL}
      onClick={advise.openAdvise}
    >
      <span className="scanner-side-nav__icon">{scannerNavIcon('advise')}</span>
      <span className="scanner-side-nav__label">{ADVISE_RAIL_LABEL}</span>
    </button>
  );
}
