/**
 * The header's screen recording chip (ADR 035): a small monitor icon with a
 * red dot while every monitor records, the details on hover; words, in red,
 * the moment the screen is not fully recorded. It controls nothing -- the
 * recording has no off switch.
 */
import { Monitor } from 'lucide-react';
import { isSampleView } from '../sample_data/sampleNav';
import { tipProps } from '../ux/hoverTip';
import { screenChip } from './screenRecordChipModel';
import { useScreenRecord, type ScreenRecordBridge } from './useScreenRecord';
import './screenRecordChip.css';

export function ScreenRecordChip({ bridge }: { bridge?: ScreenRecordBridge | null }) {
  const { desktop, view } = useScreenRecord(bridge);
  // The marketing sample desk shows no machine state of its own.
  if (isSampleView()) return null;
  const chip = screenChip(view, desktop);
  return (
    <span
      className={`screen-rec-chip screen-rec-chip--${chip.tone}`}
      data-testid="screen-rec-chip"
      data-state={view?.state ?? (desktop ? 'unknown' : 'browser')}
      role="status"
      tabIndex={0}
      aria-label={`${chip.title}: ${chip.label ?? chip.tip.split('\n')[0]}`}
      {...tipProps(chip.tip, chip.title)}
    >
      <Monitor className="screen-rec-chip__icon" aria-hidden="true" />
      <span className="screen-rec-chip__dot" aria-hidden="true" />
      {chip.label ? <span className="screen-rec-chip__label">{chip.label}</span> : null}
    </span>
  );
}
