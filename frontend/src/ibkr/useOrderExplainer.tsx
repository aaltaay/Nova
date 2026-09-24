/**
 * Hover (or keyboard focus) on a side or an order type shows what it does
 * (OrderExplainerCard.tsx). One card per ticket: `bind(kind)` goes on each
 * control, `card` is rendered once.
 *
 * The card waits `EXPLAINER_HOVER_MS` so a pointer crossing the ticket does not
 * flash it, then follows the pointer from control to control at once. A press
 * closes it -- the choice is made. Touch never opens it.
 */
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';
import { OrderExplainerCard } from './OrderExplainerCard';
import type { OrderExplainerKind } from './orderExplainerCopy';

/** Hover delay before the card shows. */
export const EXPLAINER_HOVER_MS = 350;
/** Leaving a control waits this long, so moving to the next one does not blink. */
const EXPLAINER_LEAVE_MS = 80;

export interface OrderExplainerBindings {
  onPointerEnter: (event: PointerEvent<HTMLElement>) => void;
  onPointerLeave: () => void;
  onPointerDown: () => void;
  onFocus: (event: FocusEvent<HTMLElement>) => void;
  onBlur: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  'aria-describedby'?: string;
}

export type BindOrderExplainer = (kind: OrderExplainerKind) => OrderExplainerBindings;

interface Shown {
  kind: OrderExplainerKind;
  anchor: HTMLElement;
}

function focusVisible(el: HTMLElement): boolean {
  try {
    return el.matches(':focus-visible');
  } catch {
    return false; // a DOM without :focus-visible: keyboard focus alone does not open it
  }
}

export function useOrderExplainer(): { bind: BindOrderExplainer; card: ReactNode } {
  const id = useId();
  const [shown, setShown] = useState<Shown | null>(null);
  const visible = useRef(false);
  const timers = useRef<{ show?: number; hide?: number }>({});

  useEffect(() => {
    visible.current = shown !== null;
  }, [shown]);

  const clearTimers = useCallback(() => {
    window.clearTimeout(timers.current.show);
    window.clearTimeout(timers.current.hide);
    timers.current = {};
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const hide = useCallback(() => {
    clearTimers();
    setShown(null);
  }, [clearTimers]);

  const bind = useCallback<BindOrderExplainer>(
    kind => ({
      onPointerEnter: event => {
        if (event.pointerType === 'touch') return;
        const anchor = event.currentTarget;
        clearTimers();
        if (visible.current) {
          setShown({ kind, anchor });
          return;
        }
        timers.current.show = window.setTimeout(() => setShown({ kind, anchor }), EXPLAINER_HOVER_MS);
      },
      onPointerLeave: () => {
        clearTimers();
        timers.current.hide = window.setTimeout(() => setShown(null), EXPLAINER_LEAVE_MS);
      },
      onPointerDown: hide,
      onFocus: event => {
        const anchor = event.currentTarget;
        if (!focusVisible(anchor)) return;
        clearTimers();
        setShown({ kind, anchor });
      },
      onBlur: hide,
      onKeyDown: event => {
        if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') hide();
      },
      'aria-describedby': shown?.kind === kind ? id : undefined,
    }),
    [clearTimers, hide, id, shown?.kind],
  );

  const card = shown ? (
    <OrderExplainerCard id={id} kind={shown.kind} anchor={shown.anchor} onDismiss={hide} />
  ) : null;
  return { bind, card };
}
