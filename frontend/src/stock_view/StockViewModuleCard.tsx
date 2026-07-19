/** Shared Stock View rail module chrome — bordered card + optional section title. */
import type { ReactNode } from 'react';

interface Props {
  title?: string;
  children: ReactNode;
  /** Optional right-side badge (e.g. LIVE). */
  badge?: ReactNode;
  className?: string;
  /** data-testid / aria */
  testId?: string;
  'aria-label'?: string;
}

export function StockViewModuleCard({
  title,
  children,
  badge,
  className = '',
  testId,
  'aria-label': ariaLabel,
}: Props) {
  const label = ariaLabel ?? title ?? undefined;
  return (
    <section
      className={`sv-module-card${className ? ` ${className}` : ''}`}
      data-testid={testId}
      aria-label={label}
    >
      {title ? (
        <header className="sv-module-card__head">
          <h2 className="sv-module-card__title">{title}</h2>
          {badge != null && <span className="sv-module-card__badge">{badge}</span>}
        </header>
      ) : null}
      <div className="sv-module-card__body">{children}</div>
    </section>
  );
}
