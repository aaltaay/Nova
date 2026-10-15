/**
 * One header control and the card it opens, in one positioned box, so every
 * card -- P/L, Working, TAV, the account pill -- opens directly under its own
 * button, never at the account cluster's right edge (operator report,
 * 2026-10-14). `align="end"` lines the card's right edge up with the button's,
 * for the account pill: the last control before the window's edge. `kind`
 * names the control, so a narrow header hides the whole anchor -- button,
 * open card and all (global-app-bar-responsive.css).
 */
import type { ReactNode } from 'react';

interface Props {
  kind: 'day' | 'working' | 'tav' | 'pill';
  open: boolean;
  cardId: string;
  /** The trigger button. */
  button: ReactNode;
  /** The card, rendered only while `open`. */
  children: ReactNode;
  align?: 'start' | 'end';
}

export function GlobalBarMenuAnchor({ kind, open, cardId, button, children, align = 'start' }: Props) {
  const className = [
    'global-app-bar__metric-anchor',
    `global-app-bar__metric-anchor--${kind}`,
    `global-app-bar__metric-anchor--${align}`,
  ].join(' ');
  return (
    <span className={className}>
      {button}
      {open && <div id={cardId}>{children}</div>}
    </span>
  );
}
