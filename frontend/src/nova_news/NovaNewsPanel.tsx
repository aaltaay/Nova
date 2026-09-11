/** Full-page Nova News desk. Headlines only -- not IBKR prices, not HOD. */
import { useMemo, useState } from 'react';
import type { NovaNewsCriticality, NovaNewsFilter, NovaNewsStory } from '../types/novaNews';
import { NOVA_NEWS_COLUMNS, NOVA_NEWS_LEAD_COUNT } from './constants';
import { filterStories } from './filterStories';
import { NovaNewsColumn } from './NovaNewsColumn';
import { NovaNewsLead } from './NovaNewsLead';
import { NovaNewsMasthead } from './NovaNewsMasthead';
import { SAMPLE_NOVA_NEWS_DESK } from './sampleDesk';
import { useNovaNewsDesk } from './useNovaNewsDesk';

export function NovaNewsPanel({
  selectedSymbol,
  onSelect,
  onOpenTrading,
  sampleMode = false,
}: {
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  sampleMode?: boolean;
}) {
  const [filter, setFilter] = useState<NovaNewsFilter>('all');
  const live = useNovaNewsDesk(!sampleMode);
  const desk = sampleMode ? SAMPLE_NOVA_NEWS_DESK : live.desk;
  const error = sampleMode ? null : (desk?.error || live.fetchError || null);

  const { lead, columns } = useMemo(() => {
    const stories = desk ? filterStories(desk.stories, filter) : [];
    const grouped: Record<NovaNewsCriticality, NovaNewsStory[]> = {
      critical: [],
      high: [],
      watch: [],
      background: [],
    };
    for (const story of stories) {
      grouped[story.criticality].push(story);
    }
    return {
      lead: stories.slice(0, NOVA_NEWS_LEAD_COUNT),
      columns: grouped,
    };
  }, [desk, filter]);

  return (
    <div className="nova-news" data-testid="nova-news">
      <NovaNewsMasthead desk={desk} filter={filter} onFilter={setFilter} />
      {error ? (
        <div className="empty-state" data-testid="nova-news-error">{error}</div>
      ) : !desk && live.loading ? (
        <div className="empty-state">Loading Nova News…</div>
      ) : (
        <div className="nova-news__desk">
          <NovaNewsLead
            stories={lead}
            selectedSymbol={selectedSymbol}
            onSelect={onSelect}
            onOpenTrading={onOpenTrading}
          />
          <div className="nova-news__grid" data-testid="nova-news-grid">
          {NOVA_NEWS_COLUMNS.map((band) => (
            <NovaNewsColumn
              key={band}
              band={band}
              stories={columns[band]}
              selectedSymbol={selectedSymbol}
              onSelect={onSelect}
              onOpenTrading={onOpenTrading}
            />
          ))}
          </div>
        </div>
      )}
    </div>
  );
}
