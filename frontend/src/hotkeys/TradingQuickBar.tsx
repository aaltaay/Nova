/**
 * Quick Trades: one row of icon-labelled buttons above the ticket (approved
 * Trader redesign, 2026-09-21). Every enabled Nova Action with Show button on
 * is here with its original dispatch; the short label is built from the
 * action's kind and params, the full name and key chord are the tooltip, and
 * the gear at the row's end opens Settings > Hot Keys where the row is
 * configured. Depth-dependent actions stay greyed until the L2 book is live.
 */
import { Fragment } from 'react';
import { NOVA_ACTION_DEPTH_DISABLED_REASON, NOVA_ACTION_NEEDS_DEPTH } from '../constants';
import {
  QUICK_TRADES_ARIA,
  QUICK_TRADES_CUSTOMIZE_ARIA,
  QUICK_TRADES_CUSTOMIZE_TITLE,
} from '../constantGroups/trader_chrome';
import { useSettingsOptional } from '../settings/SettingsContext';
import { formatKeyChord } from './htkFormat';
import { useHotkeyDispatchOptional } from './HotkeyDispatchContext';
import { QuickTradeGearIcon, QuickTradeIcon } from './quickTradeIcons';
import { quickTradeLabelPieces, quickTradeShortLabel, quickTradeTone } from './quickTradeLabel';
import { useTopOfBook } from './TopOfBookContext';

export function TradingQuickBar() {
  const dispatch = useHotkeyDispatchOptional();
  const settings = useSettingsOptional();
  const { topOfBook } = useTopOfBook();

  if (!dispatch) return null;

  const buttons = dispatch.novaActions.filter((a) => a.enabled && a.showButton);
  if (buttons.length === 0) return null;

  const depthOk = Boolean(
    topOfBook?.depthSubscribed && topOfBook.bid != null && topOfBook.ask != null,
  );

  return (
    <div className="nova-qt-wrap">
      <div
        className="nova-qt"
        role="toolbar"
        aria-label={QUICK_TRADES_ARIA}
        data-testid="quick-trades-row"
      >
        {buttons.map((action) => {
          const needsDepth = NOVA_ACTION_NEEDS_DEPTH.includes(action.kind);
          const disabled = needsDepth && !depthOk;
          return (
            <button
              key={action.id}
              type="button"
              className={`nova-qt__btn nova-qt__btn--${quickTradeTone(action.kind)}`}
              data-kind={action.kind}
              disabled={disabled}
              data-why={disabled ? NOVA_ACTION_DEPTH_DISABLED_REASON : undefined}
              aria-label={action.name}
              title={disabled ? undefined : `${action.name} (${formatKeyChord(action.key)})`}
              onClick={() => {
                void dispatch.runAction(action);
              }}
            >
              <QuickTradeIcon kind={action.kind} />
              {/* Each word is its own box so a label wraps only between words
                  and a word too wide for its button ends in an ellipsis (QA D14). */}
              <span className="nova-qt__label">
                {quickTradeLabelPieces(quickTradeShortLabel(action.kind, action.params)).map((piece, index) => (
                  <Fragment key={index}>
                    {piece.spaced && ' '}
                    <span className="nova-qt__word">{piece.text}</span>
                  </Fragment>
                ))}
              </span>
            </button>
          );
        })}
        {settings && (
          <button
            type="button"
            className="nova-qt__btn nova-qt__gear"
            title={QUICK_TRADES_CUSTOMIZE_TITLE}
            aria-label={QUICK_TRADES_CUSTOMIZE_ARIA}
            data-testid="quick-trades-customize"
            onClick={() => settings.openSettings('hotkeys')}
          >
            <QuickTradeGearIcon />
          </button>
        )}
      </div>
      {dispatch.lastResult && (
        <span
          className={`manual-order-result nova-qt__status ${dispatch.lastResult.ok ? 'ok' : 'err'}`}
          role="status"
        >
          {dispatch.lastResult.text}
        </span>
      )}
    </div>
  );
}
