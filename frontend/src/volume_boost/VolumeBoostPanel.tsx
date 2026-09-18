/** Scanner tab: exceptional L1 volume-rate spikes. Not a lease, not bot fire. */
import { VOLUME_BOOST_DESCRIPTION, VOLUME_BOOST_SAMPLE_NOTE } from './constants';
import { volumeBoostEmptyCopy } from './formatAge';
import { SAMPLE_VOLUME_BOOST_VIEW } from './sampleRows';
import type { VolumeBoostView } from './types';
import { useVolumeBoost } from './useVolumeBoost';
import { VolumeBoostTable } from './VolumeBoostTable';

export function VolumeBoostPanel({
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
  if (sampleMode) {
    return (
      <VolumeBoostBody
        view={SAMPLE_VOLUME_BOOST_VIEW}
        loading={false}
        fetchError={null}
        sampleMode
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
      />
    );
  }
  return (
    <VolumeBoostLive
      selectedSymbol={selectedSymbol}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
    />
  );
}

function VolumeBoostLive({
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const { view, loading, fetchError } = useVolumeBoost();
  return (
    <VolumeBoostBody
      view={view}
      loading={loading}
      fetchError={fetchError}
      sampleMode={false}
      selectedSymbol={selectedSymbol}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
    />
  );
}

function VolumeBoostBody({
  view,
  loading,
  fetchError,
  sampleMode,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  view: VolumeBoostView | null;
  loading: boolean;
  fetchError: string | null;
  sampleMode: boolean;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const rows = view?.volume_boost ?? [];
  const error = sampleMode
    ? null
    : volumeBoostEmptyCopy({
        feedError: fetchError || view?.feed_error || null,
        tableState: rows.length ? null : view?.table_state,
      });

  return (
    <div className="volume-boost-panel" data-testid="volume-boost-panel">
      <div className="volume-boost-description">
        {sampleMode ? VOLUME_BOOST_SAMPLE_NOTE : VOLUME_BOOST_DESCRIPTION}
        {view && !sampleMode ? (
          <span className="volume-boost-watched">
            {' '}
            Watching {view.watched} L1 name{view.watched === 1 ? '' : 's'}.
          </span>
        ) : null}
      </div>
      {rows.length > 0 ? (
        <VolumeBoostTable
          rows={rows}
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />
      ) : (
        <div className="empty-state" data-testid="volume-boost-empty">
          {loading && !view
            ? 'Loading volume spikes…'
            : error || 'No exceptional volume-rate spikes on the current L1 watch.'}
        </div>
      )}
    </div>
  );
}
