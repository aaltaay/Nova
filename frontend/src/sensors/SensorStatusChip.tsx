import type { SensorStatus } from './types';

const LABELS: Record<SensorStatus, string> = {
  live: 'live',
  stub: 'stub',
  computed_stub: 'computed stub',
};

export function SensorStatusChip({ status }: { status: SensorStatus }) {
  return (
    <span
      className={`sensor-chip sensor-chip--${status}`}
      data-testid={`sensor-chip-${status}`}
      data-status={status}
    >
      {LABELS[status]}
    </span>
  );
}
