import {
  HOTKEY_ACTION_LABELS,
  HOTKEY_ACTIONS,
  HOTKEY_DEFAULTS,
  HOTKEY_ORDER_ACTIONS,
} from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';

interface HotkeySettingsProps {
  mode: string;
}

/** Read-only list of default executor hotkeys (Phase G). */
export function HotkeySettings({ mode }: HotkeySettingsProps) {
  return (
    <div className="executor-hotkeys">
      <h4 className="nova-os-section-title">Hotkeys</h4>
      <p className="na-muted">
        Active while Automation is visible. Order hotkeys are disabled in{' '}
        <strong>signal</strong> mode.
      </p>
      <ul className="executor-hotkeys-list">
        {HOTKEY_ACTIONS.map((action) => {
          const blocked = mode === 'signal' && HOTKEY_ORDER_ACTIONS.includes(action);
          return (
            <li key={action} className={blocked ? 'executor-hotkeys-blocked' : undefined}>
              <kbd>{formatHotkeyLabel(HOTKEY_DEFAULTS[action])}</kbd>
              <span>{HOTKEY_ACTION_LABELS[action]}</span>
              {blocked && <span className="na-muted"> (blocked in signal)</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
