/**
 * Middle-column host for the active scanner/account/watchlist body.
 * Left rail + quote panel stay full-height; this widget stacks under the HOD
 * Momo strip. A page may hand it a board header / footer (Scanner) or rely
 * on the plain title (sample desk).
 */
import type { ReactNode } from 'react';

type Props = {
  title: string;
  children: ReactNode;
  /** Replaces the plain title line (scanner/ScannerBoardHeader). */
  header?: ReactNode;
  footer?: ReactNode;
};

export function SelectedScannerWidget({ title, children, header, footer }: Props) {
  return (
    <section
      className="scanner-selected-widget"
      data-testid="selected-scanner-widget"
      aria-label={title}
    >
      {header ?? (
        <header className="scanner-selected-widget__title" data-testid="selected-scanner-title">
          {title}
        </header>
      )}
      <div className="scanner-selected-widget__body">{children}</div>
      {footer ?? null}
    </section>
  );
}
