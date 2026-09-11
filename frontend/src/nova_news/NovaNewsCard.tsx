import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { timeAgo } from '../utils/quoteFormat';
import type { NovaNewsStory } from '../types/novaNews';

export function NovaNewsCard({
  story,
  selectedSymbol,
  onSelect,
  onOpenTrading,
  featured = false,
}: {
  story: NovaNewsStory;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  featured?: boolean;
}) {
  const age = story.published_at ? timeAgo(story.published_at) : '';
  return (
    <article
      className={`nova-news-card${featured ? ' nova-news-card--featured' : ''}`}
      data-testid={featured ? 'nova-news-lead-card' : 'nova-news-card'}
      data-criticality={story.criticality}
    >
      <div className="nova-news-card__meta">
        <span className="nova-news-card__source">{story.source}</span>
        {age ? <span className="nova-news-card__age">{age}</span> : null}
        <span className="nova-news-card__score">{story.criticality_score}</span>
      </div>
      <a
        className="nova-news-card__headline"
        href={story.url}
        target="_blank"
        rel="noopener noreferrer"
        title={story.reasons.slice(0, 4).join(' ')}
      >
        {story.headline}
      </a>
      {story.summary ? (
        <p className="nova-news-card__summary">{story.summary}</p>
      ) : null}
      {story.symbols.length > 0 ? (
        <div className="nova-news-card__symbols">
          {story.symbols.map((symbol) => (
            <SymbolSelectButton
              key={symbol}
              symbol={symbol}
              selected={selectedSymbol === symbol}
              onSelect={onSelect}
              onOpenTrading={onOpenTrading}
            />
          ))}
        </div>
      ) : null}
    </article>
  );
}
