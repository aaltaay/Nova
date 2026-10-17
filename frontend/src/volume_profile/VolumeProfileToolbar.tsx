/** The Trader toolbar's Profile switch: shows or hides the 5-minute pane's volume profile. */
import { setProfileShown, useProfileShown } from './volumeProfilePrefs';
import { VP_TOGGLE_LABEL, VP_TOGGLE_TITLE } from './volumeProfileConstants';
import './volumeProfile.css';

export function VolumeProfileToolbar() {
  const shown = useProfileShown();
  return (
    <button
      type="button"
      className={`chart-grid__optional-toggle vp-toggle${shown ? ' vp-toggle--on' : ''}`}
      aria-pressed={shown}
      title={VP_TOGGLE_TITLE}
      onClick={() => setProfileShown(!shown)}
      data-testid="volume-profile-toggle"
    >
      <span className="vp-toggle__glyph" aria-hidden="true" />
      {VP_TOGGLE_LABEL}
    </button>
  );
}
