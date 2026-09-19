import { GatewayDoorTrail } from '../ibkr/GatewayDoorTrail';
import { ActivityPanel } from './ActivityPanel';
import { ActivityTrail } from './ActivityTrail';
import { useActivityLedger } from './useActivityLedger';
import { useActivityTrail } from './useActivityTrail';

export function ActivityDashboard() {
  const ledger = useActivityLedger();
  const trail = useActivityTrail();
  return (
    <>
      <GatewayDoorTrail />
      <ActivityTrail
        items={trail.items}
        loading={trail.loading}
        error={trail.error}
        onRefresh={trail.refresh}
      />
      <ActivityPanel
        rows={ledger.rows}
        loading={ledger.loading}
        error={ledger.error}
        onRefresh={ledger.refresh}
      />
    </>
  );
}
