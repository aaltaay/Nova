import type { NovaNewsStory } from '../types/novaNews';
import { NovaNewsCard } from './NovaNewsCard';

export function NovaNewsLead({
  stories,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  stories: NovaNewsStory[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  if (stories.length === 0) return null;
  return (
    <section className="nova-news-lead" data-testid="nova-news-lead" aria-label="Top stories">
      <h2 className="nova-news-lead__title">Top of the desk</h2>
      <div className="nova-news-lead__row">
        {stories.map((story) => (
          <NovaNewsCard
            key={story.id}
            story={story}
            selectedSymbol={selectedSymbol}
            onSelect={onSelect}
            onOpenTrading={onOpenTrading}
            featured
          />
        ))}
      </div>
    </section>
  );
}
