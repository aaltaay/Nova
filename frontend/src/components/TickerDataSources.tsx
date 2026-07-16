/** Compact attribution grid: which API powers each part of the ticker panel. */
import {
  TICKER_DATA_SOURCES_SECTION_TITLE,
  TICKER_DATA_SOURCES_SECTION_HINT,
} from '../constants';
import { buildTickerDataSources } from '../utils/dataSourceMap';
import type { DataSourceInputs } from '../utils/dataSourceMap';

export function TickerDataSources({
  discoveryProvider,
  alpacaFeed,
  ibkrConnected,
}: DataSourceInputs) {
  const rows = buildTickerDataSources({
    discoveryProvider,
    alpacaFeed,
    ibkrConnected,
  });

  return (
    <section className="cq-data-sources" aria-label={TICKER_DATA_SOURCES_SECTION_TITLE}>
      <div className="cq-section-title" title={TICKER_DATA_SOURCES_SECTION_HINT}>
        {TICKER_DATA_SOURCES_SECTION_TITLE}
      </div>
      <p className="cq-data-sources-hint">{TICKER_DATA_SOURCES_SECTION_HINT}</p>
      <div className="cq-grid cq-grid-data-sources">
        {rows.map(row => (
          <div key={row.role} className="cq-cell cq-data-source-row">
            <span className="cq-label" title={row.detail}>
              {row.role}
            </span>
            <span className="cq-value" title={row.detail}>
              {row.source}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
