import type { SensorChipStatus, SensorEnvelope, SensorStatus } from './types';

const LABELS: Record<SensorChipStatus, string> = {
  live: 'live',
  stub: 'stub',
  computed_stub: 'computed stub',
  error: 'error',
};

export function sensorChipStatus(row: Pick<SensorEnvelope, 'status' | 'error'>): SensorChipStatus {
  return row.error ? 'error' : row.status;
}

export function SensorStatusChip({
  status,
  error,
}: {
  status: SensorStatus;
  error?: string;
}) {
  const chip = sensorChipStatus({ status, error });
  return (
    <span
      className={`sensor-chip sensor-chip--${chip}`}
      data-testid={`sensor-chip-${chip}`}
      data-status={chip}
    >
      {LABELS[chip]}
    </span>
  );
}
