/** The Ahead panel's scope (ADR 061): All (the AI's view), Lines (Nova's lines only), or a strategy's "what if it
 * triggers?" -- kept per viewer with the switch (`aheadPrefs.ts`). */
import { AHEAD_SCOPES } from './aheadConstants';
import { setAheadPrefs } from './aheadPrefs';
import type { AheadScope } from './aheadTypes';

const LABELS: Record<AheadScope, string> = {
  all: 'All',
  lines: 'Lines',
  flat_top: 'Flat top',
  first_pullback: 'First pullback',
};

export function ScopeSegments({ scope }: { scope: AheadScope }) {
  return (
    <div className="ahead-segs" role="radiogroup" aria-label="What Ahead shows">
      {AHEAD_SCOPES.map(id => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={scope === id}
          className={`ahead-seg${scope === id ? ' ahead-seg--on' : ''}`}
          onClick={() => setAheadPrefs({ scope: id })}
          data-testid={`ahead-scope-${id}`}
        >
          {LABELS[id]}
        </button>
      ))}
    </div>
  );
}
