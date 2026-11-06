/** The header's speaker, left of the padlock: a left click opens the sound menu, a right click mutes every Nova sound. */
import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import {
  DESK_MUTE_ARIA_MUTED,
  DESK_MUTE_ARIA_ON,
  DESK_MUTE_TITLE_MUTED,
  DESK_MUTE_TITLE_ON,
  DESK_VOICE_PROBLEM_PREFIX,
} from './constants';
import { useDeskMuted } from './deskMute';
import { DeskSoundMenu } from './DeskSoundMenu';
import { deskVoiceProblem, flipDeskMute, subscribeDeskVoiceProblem } from './speech';
import { wireStreamWindow } from './streamSound';

export function DeskSoundButton() {
  const muted = useDeskMuted();
  const problem = useSyncExternalStore(subscribeDeskVoiceProblem, deskVoiceProblem);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const title = muted
    ? DESK_MUTE_TITLE_MUTED
    : problem ? `${DESK_MUTE_TITLE_ON}\n${DESK_VOICE_PROBLEM_PREFIX} ${problem}` : DESK_MUTE_TITLE_ON;

  useEffect(() => wireStreamWindow(), []);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="global-app-bar__sound" data-testid="global-bar-sound">
      <button
        type="button"
        className={`global-app-bar__icon-btn global-app-bar__mute${muted ? ' is-muted' : ''}${problem && !muted ? ' has-problem' : ''}${open ? ' is-active' : ''}`}
        title={title}
        aria-label={muted ? DESK_MUTE_ARIA_MUTED : DESK_MUTE_ARIA_ON}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        data-testid="global-bar-mute"
        data-muted={muted}
        onClick={() => setOpen(!open)}
        onContextMenu={(e) => {
          e.preventDefault();
          flipDeskMute();
        }}
      >
        {muted
          ? <VolumeX className="global-app-bar__icon" aria-hidden />
          : <Volume2 className="global-app-bar__icon" aria-hidden />}
      </button>
      {open && <DeskSoundMenu id={menuId} />}
    </div>
  );
}
