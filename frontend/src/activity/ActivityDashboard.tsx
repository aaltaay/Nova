import { ActivityPanel } from './ActivityPanel';
import { useActivityLedger } from './useActivityLedger';

export function ActivityDashboard() {
  const { rows, loading, error, refresh } = useActivityLedger();
  return (
    <ActivityPanel rows={rows} loading={loading} error={error} onRefresh={refresh} />
  );
}
