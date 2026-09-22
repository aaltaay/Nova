/**
 * The coverage band on the context strip, scaled to the clock's own session
 * window (04:00-20:00 by default, the loaded window once a historical replay
 * narrows it): its bounds labelled as the clock states them, regular hours as
 * a lighter underlay with 09:30 / 16:00 ticks where they fall inside the
 * window, recorded stretches solid, gaps striped, a failed replay red, and the
 * green playhead. A thin amber lane under the band marks where Nova itself
 * recorded the symbol (operator ask, 2026-09-22), so a downloaded window shows
 * its Session Record too -- on the same scale. A native range input lies over
 * the track so pointer and keyboard scrubbing keep the controller's exact
 * semantics (drag locally, commit on release; keys debounce into one seek).
 * Off the live edge a small tag rides above the marker with the playhead time
 * (and date when not today) in its own lane inside the row, so the header
 * never covers it; at the edge the band shows only the marker, because the
 * global bar clock is the truth.
 */
import { SIM_STRIP_TAG_FLIP_FRACTION } from '../constantGroups/trader_chrome';
import type { RecordedLane, StripBandSegment, StripScale } from './simStripFormat';

interface Props {
  minute: number;
  max: number;
  /** Bound labels, regular-hours underlay and ticks -- from `stripScale(clock)`. */
  scale: StripScale;
  segments: StripBandSegment[];
  liveEdge: boolean;
  /** Playhead tag text off the edge; empty at the edge. */
  tag: string;
  ariaValueText: string;
  busy: boolean;
  title?: string;
  /** Where Nova recorded the band's symbol; null when the symbol or date is unknown. */
  recorded?: RecordedLane | null;
  onPointerDown: () => void;
  onChange: (minute: number) => void;
  onRelease: (minute: number) => void;
}

const pct = (fraction: number) => `${(Math.max(0, Math.min(1, fraction)) * 100).toFixed(2)}%`;

export function SimStripBand({
  minute, max, scale, segments, liveEdge, tag, ariaValueText, busy, title, recorded, onPointerDown, onChange, onRelease,
}: Props) {
  const fraction = max > 0 ? minute / max : 0;
  const flip = fraction > SIM_STRIP_TAG_FLIP_FRACTION;
  const trackTitle = [title, recorded?.title].filter(Boolean).join('\n') || undefined;
  return (
    <div className="sim-strip__band" data-testid="sim-strip-band">
      <span className="sim-strip__bound" data-testid="sim-strip-bound-open">{scale.openLabel}</span>
      <div className="sim-strip__track" title={trackTitle}>
        {scale.rth && (
          <i className="sim-strip__rth" data-testid="sim-strip-rth"
            style={{ left: pct(scale.rth.left), width: pct(scale.rth.width) }} />
        )}
        {segments.map(segment => (
          <i
            key={`${segment.kind}-${segment.left}`}
            className={`sim-strip__seg sim-strip__seg--${segment.kind}`}
            data-testid={`sim-strip-seg-${segment.kind}`}
            title={segment.title}
            style={{ left: pct(segment.left), width: pct(segment.width) }}
          />
        ))}
        {recorded && (
          <div className="sim-strip__rec" data-testid="sim-strip-recorded" data-recorded={recorded.segments.length ? 'yes' : 'no'}>
            {recorded.segments.map(segment => (
              <i
                key={segment.left}
                data-testid="sim-strip-recorded-seg"
                style={{ left: pct(segment.left), width: pct(segment.width) }}
              />
            ))}
          </div>
        )}
        {scale.ticks.map(tick => (
          <i key={tick.label} className="sim-strip__tick" data-testid="sim-strip-tick" style={{ left: pct(tick.left) }}>
            <b>{tick.label}</b>
          </i>
        ))}
        <i className={`sim-strip__play${liveEdge ? ' sim-strip__play--edge' : ''}`} data-testid="sim-strip-playhead" style={{ left: pct(fraction) }} />
        {tag && (
          <span
            className={`sim-strip__tag${flip ? ' sim-strip__tag--flip' : ''}`}
            data-testid="sim-strip-playhead-tag"
            style={{ left: pct(fraction) }}
          >
            {tag}
          </span>
        )}
        <input
          className="sim-strip__range"
          data-testid="sim-session-scrubber"
          aria-label="Sim replay time"
          aria-valuetext={ariaValueText}
          type="range"
          min={0}
          max={max}
          value={minute}
          aria-busy={busy}
          onPointerDown={onPointerDown}
          onPointerUp={event => onRelease(Number(event.currentTarget.value))}
          onPointerCancel={event => onRelease(Number(event.currentTarget.value))}
          onChange={event => onChange(Number(event.target.value))}
        />
      </div>
      <span className="sim-strip__bound" data-testid="sim-strip-bound-close">{scale.closeLabel}</span>
    </div>
  );
}
