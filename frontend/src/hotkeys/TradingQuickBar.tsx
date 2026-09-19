/**
 * DAS-style hot buttons for Nova Actions with Show button enabled.
 * Collapsible "Quick Trades" strip (persisted).
 */

import { useCallback, useEffect, useState } from 'react';
import { NOVA_ACTION_NEEDS_DEPTH } from '../constants';
import { formatKeyChord } from './htkFormat';
import { useHotkeyDispatchOptional } from './HotkeyDispatchContext';
import { useTopOfBook } from './TopOfBookContext';

const COLLAPSE_KEY = 'nova.quickTrades.collapsed';

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

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
}

export function TradingQuickBar() {
  const dispatch = useHotkeyDispatchOptional();
  const { topOfBook } = useTopOfBook();
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggle = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
      } catch {
        /* private mode */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    setCollapsed(readCollapsed());
  }, []);

  if (!dispatch) return null;

  const buttons = dispatch.novaActions.filter((a) => a.enabled && a.showButton);
  if (buttons.length === 0) return null;

  const depthOk = Boolean(
    topOfBook?.depthSubscribed && topOfBook.bid != null && topOfBook.ask != null,
  );

  return (
    <div className="nova-trading-quick-wrap">
      <button
        type="button"
        className="nova-trading-quick-toggle"
        aria-expanded={!collapsed}
        aria-controls="nova-quick-trades-body"
        onClick={toggle}
        data-testid="quick-trades-toggle"
      >
        <span className="nova-trading-quick-caret" aria-hidden>
          {collapsed ? '\u25b8' : '\u25be'}
        </span>
        <span className="nova-trading-quick-title">Quick Trades</span>
      </button>
      {!collapsed && (
        <div
          id="nova-quick-trades-body"
          className="nova-trading-quick-bar"
          role="toolbar"
          aria-label="Quick Trades"
          data-testid="quick-trades-body"
        >
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
      )}
    </div>
  );
}
