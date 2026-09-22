import {
  SENSORS_STALE,
  SENSORS_STALE_TITLE_PREFIX,
  SENSORS_STALE_TITLE_SUFFIX,
} from '../constantGroups/sensors';
import type { SensorChipStatus, SensorEnvelope, SensorStatus } from './types';

const LABELS: Record<SensorChipStatus, string> = {
  live: 'live',
  stub: 'stub',
  computed_stub: 'computed stub',
  error: 'error',
  stale: SENSORS_STALE,
};

/** A live reading computed from stale bars is stale, not live (QA W16). */
export function sensorChipStatus(
  row: Pick<SensorEnvelope, 'status' | 'error'>,
  staleSince: string | null = null,
): SensorChipStatus {
  if (row.error) return 'error';
  if (staleSince && row.status === 'live') return 'stale';
  return row.status;
}

export function SensorStatusChip({
  status,
  error,
  staleSince = null,
}: {
  status: SensorStatus;
  error?: string;
  /** ET label of the reading's newest bar when it is stale. */
  staleSince?: string | null;
}) {
  const chip = sensorChipStatus({ status, error }, staleSince);
  return (
    <span
      className={`sensor-chip sensor-chip--${chip}`}
      data-testid={`sensor-chip-${chip}`}
      data-status={chip}
      title={chip === 'stale' ? `${SENSORS_STALE_TITLE_PREFIX} ${staleSince} ${SENSORS_STALE_TITLE_SUFFIX}` : undefined}
    >
      {LABELS[chip]}
    </span>
  );
}
