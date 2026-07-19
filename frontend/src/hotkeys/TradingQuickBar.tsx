/**
 * DAS-style hot buttons for Nova Actions with Show button enabled.
 */

import { NOVA_ACTION_NEEDS_DEPTH } from '../constants';
import { formatKeyChord } from './htkFormat';
import { useHotkeyDispatchOptional } from './HotkeyDispatchContext';
import { useTopOfBook } from './TopOfBookContext';

function roleClass(kind: string): string {
  if (kind === 'cancel_symbol' || kind === 'cancel_and_exit') {
    return 'nova-quick-btn nova-quick-btn--cancel';
  }
  if (kind.startsWith('buy')) return 'nova-quick-btn nova-quick-btn--entry';
  if (kind.startsWith('sell') || kind.startsWith('exit')) {
    return 'nova-quick-btn nova-quick-btn--exit';
  }
  return 'nova-quick-btn';
}

export function TradingQuickBar() {
  const dispatch = useHotkeyDispatchOptional();
  const { topOfBook } = useTopOfBook();
  if (!dispatch) return null;

  const buttons = dispatch.novaActions.filter((a) => a.enabled && a.showButton);
  if (buttons.length === 0) return null;

  const depthOk = Boolean(
    topOfBook?.depthSubscribed && topOfBook.bid != null && topOfBook.ask != null,
  );

  return (
    <div className="nova-trading-quick-bar" role="toolbar" aria-label="Nova Action buttons">
      {buttons.map((action) => {
        const needsDepth = NOVA_ACTION_NEEDS_DEPTH.includes(action.kind);
        const disabled = needsDepth && !depthOk;
        return (
          <button
            key={action.id}
            type="button"
            className={roleClass(action.kind)}
            disabled={disabled}
            title={
              disabled
                ? 'Needs live L2 bid/ask'
                : `${action.name} (${formatKeyChord(action.key)})`
            }
            onClick={() => { void dispatch.runAction(action); }}
          >
            {action.name}
          </button>
        );
      })}
      {dispatch.lastResult && (
        <span
          className={`manual-order-result ${dispatch.lastResult.ok ? 'ok' : 'err'}`}
          role="status"
        >
          {dispatch.lastResult.text}
        </span>
      )}
    </div>
  );
}
