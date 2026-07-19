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
        Automation ladder shortcuts (System 1). Rebindable Nova Actions above are
        System 2 (manual path). Press <kbd>Ctrl+M</kbd> anytime for the full
        shortcuts menu (twice quickly to pin). Imported DAS rows never auto-run.
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
