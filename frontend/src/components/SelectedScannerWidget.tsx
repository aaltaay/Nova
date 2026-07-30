/**
 * Middle-column host for the active scanner/account/watchlist body.
 * Left rail + quote panel stay full-height; this widget stacks under HOD dock.
 */
import type { ReactNode } from 'react';

type Props = {
  title: string;
  children: ReactNode;
};

export function SelectedScannerWidget({ title, children }: Props) {
  return (
    <section
      className="scanner-selected-widget"
      data-testid="selected-scanner-widget"
      aria-label={title}
    >
      <header className="scanner-selected-widget__title" data-testid="selected-scanner-title">
        {title}
      </header>
      <div className="scanner-selected-widget__body">{children}</div>
    </section>
  );
}
