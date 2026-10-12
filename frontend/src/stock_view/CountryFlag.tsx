/**
 * The company's country beside the symbol (operator ask, 2026-10-12): Yahoo's headquarters country as its flag.
 *
 * The flags are SVGs (`country-flag-icons`) in their own chunk, loaded on first use: Windows draws no emoji flags.
 * A country with no code shows a globe that names it, a read with no country a dim globe that says so, and nothing
 * shows before the fundamentals arrive. Schema: `architecture/schema/scanner.md`, "The company's country".
 */
import { lazy, Suspense } from 'react';
import { Globe } from 'lucide-react';
import type { FundamentalsData } from '../types/ticker';

const CountryFlagSvg = lazy(() =>
  import('./CountryFlagSvg').then(m => ({ default: m.CountryFlagSvg })),
);

interface Props {
  fundamentals: FundamentalsData | null | undefined;
}

export function CountryFlag({ fundamentals }: Props) {
  // The fast first paint sends `fundamentals: {}`: no country key means not read yet, not "no country".
  if (!fundamentals || !('country' in fundamentals)) return null;
  const country = fundamentals.country ?? null;
  const code = fundamentals.country_code ?? null;
  const title = country
    ? `Headquarters: ${country} (Yahoo)`
    : 'Country not known: Yahoo gives no headquarters country';

  if (country && code) {
    return (
      <span
        className="sv-quote-card__flag"
        title={title}
        role="img"
        aria-label={title}
        data-country={code}
        data-testid="stock-view-quote-flag"
      >
        <Suspense fallback={null}>
          <CountryFlagSvg code={code} />
        </Suspense>
      </span>
    );
  }
  return (
    <span
      className={`sv-quote-card__flag sv-quote-card__flag--globe${country ? '' : ' is-unknown'}`}
      title={title}
      role="img"
      aria-label={title}
      data-testid="stock-view-quote-flag"
    >
      <Globe aria-hidden="true" />
    </span>
  );
}
