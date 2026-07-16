/** Read-only list of the six Phase G automation bindings. */
import {
  HOTKEY_ACTION_LABELS,
  HOTKEY_ACTIONS,
  HOTKEY_DEFAULTS,
  type HotkeyAction,
} from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';

export function NovaActiveShortcuts() {
  return (
    <div className="hotkey-nova-active">
      <h4 className="nova-os-section-title">Active Nova shortcuts</h4>
      <p className="na-muted">
        These run in the Automation panel only. Imported DAS rows never replace them.
      </p>
      <ul className="executor-hotkeys-list">
        {HOTKEY_ACTIONS.map((action: HotkeyAction) => (
          <li key={action}>
            <kbd>{formatHotkeyLabel(HOTKEY_DEFAULTS[action])}</kbd>
            <span>{HOTKEY_ACTION_LABELS[action]}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
