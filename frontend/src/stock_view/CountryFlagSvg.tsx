/** Every flag the desk can draw, in a chunk of its own: `CountryFlag` loads it the first time a quote names a country. */
import type { ComponentType, SVGProps } from 'react';
import * as Flags from 'country-flag-icons/react/3x2';

const FLAGS = Flags as unknown as Record<string, ComponentType<SVGProps<SVGSVGElement>> | undefined>;

export function CountryFlagSvg({ code }: { code: string }) {
  const Flag = FLAGS[code];
  // A code this package version has no flag for reads as the code itself, never another country's flag.
  return Flag ? <Flag aria-hidden="true" /> : <span className="sv-quote-card__flag-code">{code}</span>;
}
