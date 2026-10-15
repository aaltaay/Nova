/**
 * One header control and the card it opens, in one positioned box, so every
 * card -- P/L, Working, TAV, the account pill -- opens directly under its own
 * button, never at the account cluster's right edge (operator report,
 * 2026-10-14). `align="end"` lines the card's right edge up with the button's,
 * for the account pill: the last control before the window's edge.
 */
import type { ReactNode } from 'react';

interface Props {
  open: boolean;
  cardId: string;
  /** The trigger button. */
  button: ReactNode;
  /** The card, rendered only while `open`. */
  children: ReactNode;
  align?: 'start' | 'end';
}

export function GlobalBarMenuAnchor({ open, cardId, button, children, align = 'start' }: Props) {
  return (
    <span className={`global-app-bar__metric-anchor global-app-bar__metric-anchor--${align}`}>
      {button}
      {open && <div id={cardId}>{children}</div>}
    </span>
  );
}
