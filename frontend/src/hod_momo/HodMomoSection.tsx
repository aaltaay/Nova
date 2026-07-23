/**
 * Memoized HOD Momo / Running Up tab body — isolated from TabModuleHost's
 * `nowSec` prop (the 1Hz scanner-table age clock) so that unrelated tick does
 * not force this subtree to reconcile every second. Only re-renders when its
 * own props (alerts, config, connection state, selection) actually change.
 */
import { memo, useCallback, useMemo } from 'react';
import { HodMomoTab } from './HodMomoTab';
import { RunningUpTab } from './RunningUpTab';
import { HodMomoSettings } from './HodMomoSettings';
import { partitionScannerAlerts } from './scannerPartition';
import type { useHodMomoConfig } from './useHodMomoConfig';
import type { useHodMomoStream } from './useHodMomoStream';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { alertApp, confirmApp } from '../ux';

type HodStream = ReturnType<typeof useHodMomoStream>;
type HodConfig = ReturnType<typeof useHodMomoConfig>;

export interface HodMomoSectionProps {
  activeTab: 'hod_momo' | 'running_up';
  hodMomoStream: HodStream;
  hodMomoConfig: HodConfig;
  selectedSymbol: string | null;
  onSelect: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
  showHodSettings: boolean;
  onToggleHodSettings: () => void;
  onCloseHodSettings: () => void;
}

function HodMomoSectionImpl({
  activeTab,
  hodMomoStream,
  hodMomoConfig,
  selectedSymbol,
  onSelect,
  onOpenTrading,
  showHodSettings,
  onToggleHodSettings,
  onCloseHodSettings,
}: HodMomoSectionProps) {
  const sample = useSampleDataOptional();
  const { hodMomentum, runningUp } = useMemo(
    () => partitionScannerAlerts(hodMomoStream.alerts),
    [hodMomoStream.alerts],
  );

  const clearSharedAlerts = useCallback((scannerLabel: string) => {
    if (sample) {
      void alertApp({
        title: 'Sample data',
        message: `${scannerLabel} alerts are fixtures; nothing is cleared on the server.`,
      });
      return;
    }
    void confirmApp({
      title: `Clear today's ${scannerLabel} alerts?`,
      message:
        'This clears the shared HOD Momentum + Running Up alert store for today. '
        + 'Past days in History are kept. New alerts will keep arriving.',
      confirmLabel: 'Clear',
      tone: 'warning',
    }).then(ok => {
      if (!ok) return;
      novaFetch(`${API_BASE_URL}/api/hod-momo/alerts`, { method: 'DELETE' }).catch(err => {
        console.error('Clear HOD/Running Up alerts failed', err);
      });
    });
  }, [sample]);

  const onClearHodMomentum = useCallback(() => clearSharedAlerts('HOD Momentum'), [clearSharedAlerts]);
  const onClearRunningUp = useCallback(() => clearSharedAlerts('Running Up'), [clearSharedAlerts]);

  return (
    <>
      {showHodSettings && (
        <HodMomoSettings config={hodMomoConfig} onClose={onCloseHodSettings} />
      )}
      {activeTab === 'hod_momo' ? (
        <HodMomoTab
          alerts={hodMomentum}
          totalToday={hodMomentum.length}
          connected={hodMomoStream.connected}
          config={hodMomoConfig}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelect}
          onOpenTrading={onOpenTrading}
          onOpenSettings={onToggleHodSettings}
          onClearAlerts={onClearHodMomentum}
        />
      ) : (
        <RunningUpTab
          alerts={runningUp}
          totalToday={runningUp.length}
          connected={hodMomoStream.connected}
          config={hodMomoConfig}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelect}
          onOpenTrading={onOpenTrading}
          onOpenSettings={onToggleHodSettings}
          onClearAlerts={onClearRunningUp}
        />
      )}
    </>
  );
}

export const HodMomoSection = memo(HodMomoSectionImpl);
