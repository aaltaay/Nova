import type { NovaNewsDesk, NovaNewsFilter } from '../types/novaNews';
import {
  NOVA_NEWS_FILTER_LABELS,
  NOVA_NEWS_FILTERS,
  NOVA_NEWS_TAGLINE,
  NOVA_NEWS_TITLE,
} from './constants';

export function NovaNewsMasthead({
  desk,
  filter,
  onFilter,
}: {
  desk: NovaNewsDesk | null;
  filter: NovaNewsFilter;
  onFilter: (next: NovaNewsFilter) => void;
}) {
  const total = desk?.counts.total ?? 0;
  const live = desk?.sources.filter((s) => s.ok).length ?? 0;
  const sources = desk?.sources.length ?? 0;
  return (
    <header className="nova-news-masthead" data-testid="nova-news-masthead">
      <div className="nova-news-masthead__brand">
        <h1 className="nova-news-masthead__title">{NOVA_NEWS_TITLE}</h1>
        <p className="nova-news-masthead__tagline">{NOVA_NEWS_TAGLINE}</p>
      </div>
      <div className="nova-news-masthead__stats">
        <span>{total} stories</span>
        <span>
          {live} of {sources} sources live
        </span>
      </div>
      <div className="nova-news-masthead__filters" role="tablist" aria-label="Nova News filters">
        {NOVA_NEWS_FILTERS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            className={`nova-news-filter${filter === key ? ' is-active' : ''}`}
            onClick={() => onFilter(key)}
          >
            {NOVA_NEWS_FILTER_LABELS[key]}
          </button>
        ))}
      </div>
      {desk ? (
        <ul className="nova-news-masthead__sources">
          {desk.sources.map((src) => (
            <li
              key={src.id}
              className={`nova-news-source${src.ok ? ' is-live' : ' is-down'}`}
              title={src.error ?? `${src.count} headlines`}
            >
              {src.label}
              <span>{src.ok ? `${src.count}` : 'down'}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </header>
  );
}
