/**
 * Read-only summary list on Settings → Hot Keys (Webull-style landing).
 */

import { HOTKEYS_EMPTY_LIST } from '../constants';
import { formatKeyChord } from './htkFormat';
import { formatNovaActionListLabel } from './novaActionFormat';
import type { NovaActionRecord } from './novaActionTypes';

export function HotkeysLandingList({
  actions,
  onOpenAction,
}: {
  actions: NovaActionRecord[];
  onOpenAction: (id: string) => void;
}) {
  if (actions.length === 0) {
    return <p className="na-muted hk-landing-empty">{HOTKEYS_EMPTY_LIST}</p>;
  }

  return (
    <ul className="hk-landing-list" data-testid="hotkeys-landing-list">
      {actions.map((row) => (
        <li key={row.id}>
          <button
            type="button"
            className="hk-landing-row"
            onClick={() => onOpenAction(row.id)}
          >
            <span className="hk-landing-row-label">
              {formatNovaActionListLabel(row)}
              {!row.enabled && (
                <span className="na-muted"> (off)</span>
              )}
            </span>
            <kbd className="hk-landing-chord">
              {row.key.key ? formatKeyChord(row.key) : '-'}

            </kbd>
          </button>
        </li>
      ))}
    </ul>
  );
}
