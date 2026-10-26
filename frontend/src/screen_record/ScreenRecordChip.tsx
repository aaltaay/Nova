/**
 * The header's screen recording chip (ADR 035, ADR 067): a muted monitor with
 * a slash and "Screen rec paused" while the recording is paused (the default),
 * a small monitor icon with a red dot while every monitor records, the details
 * on hover; words, in red, the moment a recording that is on misses a monitor.
 * It controls nothing: NOVA_SCREEN_RECORD, read when the desktop app starts,
 * decides whether the screen is recorded.
 */
import { Monitor, MonitorOff } from 'lucide-react';
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
  const off = chip.tone === 'off';
  const Icon = off ? MonitorOff : Monitor;
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
      <Icon className="screen-rec-chip__icon" aria-hidden="true" />
      {off ? null : <span className="screen-rec-chip__dot" aria-hidden="true" />}
      {chip.label ? <span className="screen-rec-chip__label">{chip.label}</span> : null}
    </span>
  );
}
