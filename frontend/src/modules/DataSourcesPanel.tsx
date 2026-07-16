/** Data-source attribution panel — reads discovery/feed from workspace. */
import { TickerDataSources } from '../components/TickerDataSources';
import { useWorkspace } from '../workspace';

export function DataSourcesPanel() {
  const { discoveryProvider, alpacaFeed, ibkrConnected } = useWorkspace();
  return (
    <div className="nova-module nova-module--data-sources" data-module="data-sources">
      <TickerDataSources
        discoveryProvider={discoveryProvider}
        alpacaFeed={alpacaFeed}
        ibkrConnected={ibkrConnected}
      />
    </div>
  );
}
