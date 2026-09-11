import type { NovaNewsCriticality, NovaNewsStory } from '../types/novaNews';
import { NOVA_NEWS_COLUMN_HINTS, NOVA_NEWS_COLUMN_LABELS } from './constants';
import { NovaNewsCard } from './NovaNewsCard';

export function NovaNewsColumn({
  band,
  stories,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  band: NovaNewsCriticality;
  stories: NovaNewsStory[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  return (
    <section
      className={`nova-news-column nova-news-column--${band}`}
      data-testid={`nova-news-column-${band}`}
    >
      <header className="nova-news-column__header" title={NOVA_NEWS_COLUMN_HINTS[band]}>
        <h2 className="nova-news-column__title">{NOVA_NEWS_COLUMN_LABELS[band]}</h2>
        <span className="nova-news-column__count">{stories.length}</span>
      </header>
      <div className="nova-news-column__body">
        {stories.length === 0 ? (
          <p className="nova-news-column__empty">No stories in this band.</p>
        ) : (
          stories.map((story) => (
            <NovaNewsCard
              key={story.id}
              story={story}
              selectedSymbol={selectedSymbol}
              onSelect={onSelect}
              onOpenTrading={onOpenTrading}
            />
          ))
        )}
      </div>
    </section>
  );
}
