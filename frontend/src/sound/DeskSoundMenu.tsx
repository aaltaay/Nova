/**
 * The sound menu under the header's speaker (operator ask, 2026-11-05; approved mockup v1): All sounds, then each sound
 * in its section with a switch, a volume and Play. Display only. Schema: desk-ops.md, "The sound menu".
 */
import {
  Bell,
  LayoutGrid,
  Mic,
  Play,
  Target,
  TrendingUp,
  TriangleAlert,
  TvMinimalPlay,
  Volume2,
  VolumeX,
  type LucideIcon,
} from 'lucide-react';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import {
  DESK_MUTE_REASON,
  DESK_SOUND_ALL_LABEL,
  DESK_SOUND_LEVEL_MAX,
  DESK_SOUND_LEVEL_ZERO,
  DESK_SOUND_SECTIONS,
  DESK_SOUND_TIPS,
  DESK_STREAM_LIVE,
  DESK_STREAM_NOT_OPEN,
  DESK_STREAM_OFF_AIR,
  type DeskSoundId,
} from './constants';
import { useDeskMuted } from './deskMute';
import { deskSoundAudible, setDeskSoundLevel, setDeskSoundOn, useDeskSoundLevel, useDeskSoundOn } from './deskSounds';
import { flipDeskMute } from './speech';
import { useStreamPlayerState, useStreamPopOutOpen } from './streamSound';
import { previewDeskSound } from './tones';

const ICONS: Record<DeskSoundId, LucideIcon> = {
  hod: TrendingUp,
  setups: Target,
  topNine: LayoutGrid,
  voice: Mic,
  calls: Bell,
  alarm: TriangleAlert,
  stream: TvMinimalPlay,
};

interface SwitchProps {
  on: boolean;
  label: string;
  testId: string;
  onFlip: () => void;
  why?: string | null;
}

function SoundSwitch({ on, label, testId, onFlip, why = null }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`desk-sound-switch${on ? ' is-on' : ''}`}
      disabled={why !== null}
      {...whyProps(why !== null, why)}
      data-testid={testId}
      onClick={onFlip}
    />
  );
}

/** Why the YouTube row is locked, or null while a player has the stream. */
function useStreamLock(): string | null {
  const player = useStreamPlayerState();
  const popOut = useStreamPopOutOpen();
  if (popOut || player === 'live') return null;
  return player === 'offline' ? DESK_STREAM_OFF_AIR : DESK_STREAM_NOT_OPEN;
}

function SoundRow({ id, label, tile }: { id: DeskSoundId; label: string; tile: string }) {
  const on = useDeskSoundOn(id);
  const level = useDeskSoundLevel(id);
  const muted = useDeskMuted();
  const streamLock = useStreamLock();
  const isStream = id === 'stream';
  const lock = isStream ? streamLock : null;
  const playWhy = muted ? DESK_MUTE_REASON : level === 0 ? DESK_SOUND_LEVEL_ZERO : null;
  const Icon = ICONS[id];
  const hearIt = () => {
    if (!isStream && deskSoundAudible(id)) previewDeskSound(id);
  };
  return (
    <div className={`desk-sound-row${on && !muted ? '' : ' is-dim'}`} data-testid={`desk-sound-row-${id}`}>
      <span className={`desk-sound-row__tile desk-sound-row__tile--${tile}`}><Icon aria-hidden /></span>
      <span className="desk-sound-row__label" {...tipProps(lock ?? DESK_SOUND_TIPS[id] ?? null, label)}>{label}</span>
      {isStream && lock === null && <span className="desk-sound-row__live" data-testid="desk-sound-live">{DESK_STREAM_LIVE}</span>}
      <input
        type="range"
        className="desk-sound-row__level"
        min={0}
        max={DESK_SOUND_LEVEL_MAX}
        step={1}
        value={level}
        aria-label={`${label} volume`}
        disabled={lock !== null}
        {...whyProps(lock !== null, lock)}
        data-testid={`desk-sound-level-${id}`}
        onChange={e => setDeskSoundLevel(id, Number(e.target.value))}
        onPointerUp={hearIt}
        onKeyUp={hearIt}
      />
      <span className="desk-sound-row__pct">{level}</span>
      {isStream ? <span className="desk-sound-row__play-gap" /> : (
        <button
          type="button"
          className="desk-sound-row__play"
          aria-label={`Hear ${label}`}
          disabled={playWhy !== null}
          {...whyProps(playWhy !== null, playWhy)}
          data-testid={`desk-sound-play-${id}`}
          onClick={() => previewDeskSound(id)}
        >
          <Play aria-hidden />
        </button>
      )}
      <SoundSwitch on={on} label={label} testId={`desk-sound-switch-${id}`} why={lock} onFlip={() => setDeskSoundOn(id, !on)} />
    </div>
  );
}

export function DeskSoundMenu({ id }: { id: string }) {
  const muted = useDeskMuted();
  const AllIcon = muted ? VolumeX : Volume2;
  return (
    <div id={id} className="global-app-bar__card desk-sound-menu" role="group" aria-label="Sound menu" data-testid="desk-sound-menu">
      <div className="desk-sound-menu__all">
        <AllIcon aria-hidden />
        <span>{DESK_SOUND_ALL_LABEL}</span>
        <SoundSwitch on={!muted} label={DESK_SOUND_ALL_LABEL} testId="desk-sound-all" onFlip={flipDeskMute} />
      </div>
      {DESK_SOUND_SECTIONS.map(section => (
        <section key={section.title} aria-label={section.title}>
          <div className="desk-sound-menu__section">{section.title}</div>
          {section.rows.map(row => <SoundRow key={row.id} id={row.id} label={row.label} tile={section.tile} />)}
        </section>
      ))}
    </div>
  );
}
