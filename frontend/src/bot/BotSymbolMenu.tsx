/**
 * The one right-click symbol menu for every ticker list and Trader tab
 * (operator ask, 2026-09-23: "it's so hard to even know they are clickable").
 * The symbol is named once in the head; each action is a row that looks like a
 * button -- an icon tile in the action's colour, a label that says what the
 * click does, a line saying what that means, and a state chip when it is
 * already on (Watching, REC, On). Stopping a recording stays a hold.
 */
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { Bot, BotOff, Circle, Pin, PinOff, Square, TriangleAlert } from 'lucide-react';
import {
  BOT_ALLOWLIST_ADD,
  BOT_ALLOWLIST_REMOVE,
  SYMBOL_MENU_ALLOW_HINT,
  SYMBOL_MENU_ALLOW_STATE,
  SYMBOL_MENU_CAPTION,
  SYMBOL_MENU_PIN_HINT,
  SYMBOL_MENU_REC_STATE,
  SYMBOL_MENU_RECORD,
  SYMBOL_MENU_RECORD_HINT,
  SYMBOL_MENU_STOP_RECORD,
  SYMBOL_MENU_UNALLOW_HINT,
  SYMBOL_MENU_UNPIN_HINT,
  SYMBOL_MENU_UNWATCH_HINT,
  SYMBOL_MENU_WATCH_HINT,
  SYMBOL_MENU_WATCH_STATE,
} from '../constantGroups/bot';
import { TRADER_TAB_PIN_LABEL, TRADER_TAB_UNPIN_LABEL } from '../constantGroups/trader_view';
import {
  closeBotSymbolMenu,
  subscribeBotSymbolMenu,
  type BotSymbolMenuOpen,
} from './botSymbolMenuStore';
import { useBotAllowlist } from './useBotAllowlist';
import {
  getRecordingSymbols,
  getSessionRecordError,
  isTabRecording,
  startTabRecord,
  stopTabRecord,
  subscribeSessionRecord,
} from '../capture/sessionRecordStore';
import { HoldToStopButton } from '../capture/HoldToStopButton';
import { CAPTURE_STOP_HOLD_HINT, captureStopHoldLabel } from '../capture/constants';
import { botSymbolMenuPosition } from './botSymbolMenuPlacement';
import {
  toggleWatchList,
  useWatchList,
  WATCH_LIST_ADD,
  WATCH_LIST_REMOVE,
  WatchEyeIcon,
} from '../watch_list';
import './symbolMenu.css';

type Tone = 'tab' | 'watch' | 'rec' | 'bot';
const ICON_PX = 15;

/** Icon tile, label, the line under it, and the chip that says it is already on. */
function RowBody({ tone, icon, label, hint, state }: {
  tone: Tone; icon: ReactNode; label: string; hint: string; state?: string | null;
}) {
  return (
    <>
      <span className={`symbol-menu__icon symbol-menu__icon--${tone}`} aria-hidden="true">{icon}</span>
      <span className="symbol-menu__text">
        <span className="symbol-menu__label">{label}</span>
        <span className="symbol-menu__hint">{hint}</span>
      </span>
      {state ? <span className={`symbol-menu__state symbol-menu__state--${tone}`}>{state}</span> : null}
    </>
  );
}

function MenuRow({ tone, icon, label, hint, state, testId, disabled, onClick }: {
  tone: Tone; icon: ReactNode; label: string; hint: string; state?: string | null;
  testId: string; disabled?: boolean; onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      className={`symbol-menu__row symbol-menu__row--${tone}${state ? ' is-on' : ''}`}
      data-testid={testId}
      disabled={disabled}
      onClick={onClick}
    >
      <RowBody tone={tone} icon={icon} label={label} hint={hint} state={state} />
    </button>
  );
}

/** ↑ / ↓ / Home / End move between rows once focus is inside the menu. */
function moveFocus(event: ReactKeyboardEvent<HTMLDivElement>): void {
  const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
  if (!keys.includes(event.key)) return;
  const rows = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)'));
  if (rows.length === 0) return;
  event.preventDefault();
  const at = rows.indexOf(document.activeElement as HTMLButtonElement);
  const next = event.key === 'Home' ? 0
    : event.key === 'End' ? rows.length - 1
      : event.key === 'ArrowDown' ? (at + 1) % rows.length
        : (at <= 0 ? rows.length - 1 : at - 1);
  rows[next].focus();
}

export function BotSymbolMenuHost() {
  const [open, setOpen] = useState<BotSymbolMenuOpen>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [recordBusy, setRecordBusy] = useState(false);
  const [menuHeight, setMenuHeight] = useState(0);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const { isAllowed, add, remove } = useBotAllowlist();
  const watchList = useWatchList();
  const recordEpoch = useSyncExternalStore(
    subscribeSessionRecord,
    () => `${getRecordingSymbols().join(',')}|${getSessionRecordError() || ''}`,
    () => '',
  );

  useEffect(() => subscribeBotSymbolMenu(value => {
    setRecordError(null);
    setMenuHeight(0);
    setOpen(value);
  }), []);

  // Measure before paint, so a right-click low on the screen opens upward in one
  // frame; again whenever a row or the error line changes the menu's height.
  useLayoutEffect(() => {
    const height = menuRef.current?.getBoundingClientRect().height ?? 0;
    if (height > 0 && Math.abs(height - menuHeight) > 1) setMenuHeight(height);
  }, [open, menuHeight, recordError, recordEpoch, watchList]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeBotSymbolMenu();
    };
    const onDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-testid="bot-symbol-menu"]')) return;
      closeBotSymbolMenu();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  if (!open) return null;
  const { symbol } = open;
  const allowed = isAllowed(symbol);
  const watched = watchList.includes(symbol);
  const recording = isTabRecording(symbol);
  void recordEpoch;
  const toggleRecord = async (stop: boolean) => {
    setRecordBusy(true);
    setRecordError(null);
    const err = stop ? await stopTabRecord(symbol) : await startTabRecord(symbol);
    setRecordBusy(false);
    if (err) {
      setRecordError(err);
      return;
    }
    closeBotSymbolMenu();
  };
  const error = recordError || getSessionRecordError(symbol);

  // Below the app bar, never over the Sim session bar under the tabs; wholly on screen.
  const appBar = document.querySelector('[data-testid="global-app-bar"]');
  const position = botSymbolMenuPosition({
    x: open.x,
    y: open.y,
    appBarBottom: appBar ? appBar.getBoundingClientRect().bottom : null,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    menuHeight,
  });
  return (
    <div
      ref={menuRef}
      className="bot-symbol-menu symbol-menu"
      role="menu"
      aria-label={`${symbol} ${SYMBOL_MENU_CAPTION}`}
      data-testid="bot-symbol-menu"
      style={{ top: position.top, left: position.left }}
      onKeyDown={moveFocus}
      onContextMenu={event => event.preventDefault()}
    >
      <div className="symbol-menu__head">
        <span className="symbol-menu__sym" data-testid="bot-symbol-menu-symbol">{symbol}</span>
        <span className="symbol-menu__caption">{SYMBOL_MENU_CAPTION}</span>
      </div>
      {open.tab && (
        // Opened from a Trader tab: pin / unpin it (ADR 011 preview tabs).
        <MenuRow
          tone="tab"
          testId="bot-symbol-menu-pin"
          icon={open.tab.pinned ? <PinOff size={ICON_PX} /> : <Pin size={ICON_PX} />}
          label={open.tab.pinned ? TRADER_TAB_UNPIN_LABEL : TRADER_TAB_PIN_LABEL}
          hint={open.tab.pinned ? SYMBOL_MENU_UNPIN_HINT : SYMBOL_MENU_PIN_HINT}
          onClick={() => {
            open.tab?.onTogglePin();
            closeBotSymbolMenu();
          }}
        />
      )}
      <MenuRow
        tone="watch"
        testId="bot-symbol-menu-watch"
        icon={<WatchEyeIcon />}
        label={watched ? WATCH_LIST_REMOVE : WATCH_LIST_ADD}
        hint={watched ? SYMBOL_MENU_UNWATCH_HINT : SYMBOL_MENU_WATCH_HINT}
        state={watched ? SYMBOL_MENU_WATCH_STATE : null}
        onClick={() => {
          toggleWatchList(symbol);
          closeBotSymbolMenu();
        }}
      />
      {recording ? (
        // A recording is locked: Stop takes a deliberate hold, never a slip.
        <HoldToStopButton
          testId="bot-symbol-menu-record"
          className="symbol-menu__row symbol-menu__row--rec is-on"
          label={captureStopHoldLabel(symbol)}
          disabled={recordBusy}
          onConfirm={() => void toggleRecord(true)}
        >
          <RowBody
            tone="rec"
            icon={<Square size={ICON_PX - 3} fill="currentColor" />}
            label={SYMBOL_MENU_STOP_RECORD}
            hint={CAPTURE_STOP_HOLD_HINT}
            state={SYMBOL_MENU_REC_STATE}
          />
        </HoldToStopButton>
      ) : (
        <MenuRow
          tone="rec"
          testId="bot-symbol-menu-record"
          icon={<Circle size={ICON_PX - 3} fill="currentColor" />}
          label={SYMBOL_MENU_RECORD}
          hint={SYMBOL_MENU_RECORD_HINT}
          disabled={recordBusy}
          onClick={() => void toggleRecord(false)}
        />
      )}
      {error && (
        <div className="symbol-menu__error" role="alert">
          <TriangleAlert size={13} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}
      <MenuRow
        tone="bot"
        testId="bot-symbol-menu-toggle"
        icon={allowed ? <BotOff size={ICON_PX} /> : <Bot size={ICON_PX} />}
        label={allowed ? BOT_ALLOWLIST_REMOVE : BOT_ALLOWLIST_ADD}
        hint={allowed ? SYMBOL_MENU_UNALLOW_HINT : SYMBOL_MENU_ALLOW_HINT}
        state={allowed ? SYMBOL_MENU_ALLOW_STATE : null}
        onClick={() => {
          void (allowed ? remove(symbol) : add(symbol));
          closeBotSymbolMenu();
        }}
      />
    </div>
  );
}
