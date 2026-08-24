import { ActivityPanel } from './ActivityPanel';
import { useActivityLedger } from './useActivityLedger';
import { GatewayDoorTrail } from '../ibkr/GatewayDoorTrail';

export function ActivityDashboard() {
  const { rows, loading, error, refresh } = useActivityLedger();
  return (
    <>
      <GatewayDoorTrail />
      <ActivityPanel rows={rows} loading={loading} error={error} onRefresh={refresh} />
    </>
  );
}
