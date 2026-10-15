/**
 * The stream the feed reads, playing above the Activity (operator, 2026-10-13: "have a shortcut button to open that
 * channel ... or maybe inside Nova itself"). YouTube's embedded player, muted to start; mute / unmute talks to
 * it over YouTube's IFrame API. Pop out opens it in a window of its own, Open on YouTube in the browser, and close
 * hides it for this window until Watch live. YouTube asks the desk's network to sign in before it plays ("confirm
 * you're not a bot"): on the desktop, Sign in to YouTube opens Google's own page in a window of its own, and the player
 * reloads when it closes (electron/streamPlayer.mjs). It plays only while the feed is reading the stream live; off air
 * it keeps its size and shows OFFLINE with why in place of the video, so an ended stream's recording never plays as if
 * it were live (operator, 2026-10-13: "dont shrink the display keep it just have icon that says OFFLINE"). The header
 * mute (sound/) mutes the player and holds its Sound on button, saying why. Nothing here reads or trades anything.
 */
import { useEffect, useRef, useState } from 'react';
import { DESK_MUTE_REASON, useDeskMuted } from '../sound';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import {
  FT_LAST_STREAM,
  FT_STREAM_CLOSE,
  FT_STREAM_LIVE,
  FT_STREAM_LIVE_ONLY,
  FT_STREAM_MUTE,
  FT_STREAM_MUTED,
  FT_STREAM_OFFLINE,
  FT_STREAM_POP_OUT,
  FT_STREAM_POP_OUT_TIP,
  FT_STREAM_RELOAD,
  FT_STREAM_SIGN_IN,
  FT_STREAM_SIGN_IN_TIP,
  FT_STREAM_SOUND_ON,
  FT_STREAM_TITLE,
  FT_STREAM_UNMUTE,
  FT_STREAM_YOUTUBE,
} from './constants';
import { embedUrl, openStreamOnYouTube, playerCommand, popOutStream, setStreamOpen } from './stream';

interface Props {
  videoId: string;
  title: string | null;
  /** Why the stream is offline (capture.offAirWhy), or null while it is on air (capture.onAir). */
  offAir: string | null;
}

export function StreamPlayer({ videoId, title, offAir }: Props) {
  const live = offAir === null;
  const frame = useRef<HTMLIFrameElement>(null);
  const [muted, setMuted] = useState(true);
  // Back on air the player is a new one, muted to start.
  const [wasLive, setWasLive] = useState(live);
  if (wasLive !== live) {
    setWasLive(live);
    setMuted(true);
  }
  // A new key reloads the player: after a sign-in, or by hand.
  const [load, setLoad] = useState(0);
  const reload = () => {
    setMuted(true);
    setLoad((n) => n + 1);
  };
  useEffect(() => window.novaDesktop?.onYoutubeSignedIn?.(() => {
    setMuted(true);
    setLoad((n) => n + 1);
  }), []);
  const signIn = window.novaDesktop?.youtubeSignIn;
  const deskMuted = useDeskMuted();
  // The header mute silences the stream as it does every Nova sound.
  useEffect(() => {
    if (!deskMuted || muted) return;
    frame.current?.contentWindow?.postMessage(playerCommand('mute'), '*');
    setMuted(true);
  }, [deskMuted, muted]);
  const toggleSound = () => {
    frame.current?.contentWindow?.postMessage(playerCommand(muted ? 'unMute' : 'mute'), '*');
    setMuted(!muted);
  };
  return (
    <section className="ft-card ft-stream" aria-label={FT_STREAM_TITLE} data-testid="ft-stream" data-on-air={live}>
      <div className="ft-stream__screen">
        {live ? (
          <iframe key={load} ref={frame} className="ft-stream__frame" src={embedUrl(videoId)} title={title ?? FT_STREAM_TITLE}
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin" data-testid="ft-stream-frame" />
        ) : (
          <div className="ft-stream__offline" {...tipProps(FT_STREAM_LIVE_ONLY)} data-testid="ft-stream-offline">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              strokeLinecap="round" aria-hidden="true">
              <path d="M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8M8.8 8.8a4.5 4.5 0 0 0 0 6.4M15.2 8.8a4.5 4.5 0 0 1 0 6.4" />
              <circle cx="12" cy="12" r="1.3" />
              <path d="M3.5 3.5l17 17" />
            </svg>
            <span className="ft-stream__offline-word">{FT_STREAM_OFFLINE}</span>
            <span className="ft-xs" data-testid="ft-stream-off-why">{offAir}</span>
          </div>
        )}
        {live && <span className="ft-stream__live">{FT_STREAM_LIVE}</span>}
        <div className="ft-stream__tools">
          {live && (
            <>
              <button type="button" className="ft-btn ft-btn--overlay" onClick={toggleSound} aria-pressed={!muted}
                disabled={deskMuted} {...whyProps(deskMuted, DESK_MUTE_REASON)}
                {...(deskMuted ? {} : tipProps(muted ? FT_STREAM_UNMUTE : FT_STREAM_MUTE))} data-testid="ft-stream-sound">
                {muted ? `🔇 ${FT_STREAM_MUTED}` : `🔊 ${FT_STREAM_SOUND_ON}`}
              </button>
              <button type="button" className="ft-btn ft-btn--overlay" onClick={reload} aria-label={FT_STREAM_RELOAD}
                {...tipProps(FT_STREAM_RELOAD)} data-testid="ft-stream-reload">↻</button>
              <button type="button" className="ft-btn ft-btn--overlay" onClick={() => popOutStream(videoId)}
                {...tipProps(FT_STREAM_POP_OUT_TIP)} data-testid="ft-stream-popout">⧉ {FT_STREAM_POP_OUT}</button>
            </>
          )}
          <button type="button" className="ft-btn ft-btn--overlay" onClick={() => setStreamOpen(false)}
            aria-label={FT_STREAM_CLOSE} {...tipProps(FT_STREAM_CLOSE)} data-testid="ft-stream-close">✕</button>
        </div>
      </div>
      <div className="ft-stream__foot">
        <span className="ft-muted ft-small ft-ellipsis">{live || !title ? title : `${FT_LAST_STREAM} ${title}`}</span>
        {live && signIn && (
          <button type="button" className="ft-link ft-small ft-nowrap" {...tipProps(FT_STREAM_SIGN_IN_TIP)}
            onClick={() => void signIn().catch((e: unknown) => console.warn('[nova] YouTube sign-in failed', e))}
            data-testid="ft-stream-sign-in">{FT_STREAM_SIGN_IN}</button>
        )}
        {live && (
          <button type="button" className="ft-link ft-small ft-nowrap" onClick={() => openStreamOnYouTube(videoId)}
            data-testid="ft-stream-youtube">{FT_STREAM_YOUTUBE} ↗</button>
        )}
      </div>
    </section>
  );
}
