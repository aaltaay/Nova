import type { OrderFillAudit } from './types';
import {
  fillLatencyFaceMs,
  fillLatencyTone,
  fillLatencyTooltip,
  formatFillLatencyMs,
} from './orderFillLatency';

export function FillLatencyTd({
  audit,
}: {
  audit?: OrderFillAudit | null;
}) {
  const tone = fillLatencyTone(audit);
  const className = [
    'ibkr-col--num',
    'ibkr-fill-latency',
    tone ? `ibkr-fill-latency--${tone}` : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <td
      className={className}
      title={fillLatencyTooltip(audit)}
      data-level={tone ?? undefined}
      data-testid="ibkr-fill-latency"
    >
      {formatFillLatencyMs(fillLatencyFaceMs(audit))}
    </td>
  );
}
