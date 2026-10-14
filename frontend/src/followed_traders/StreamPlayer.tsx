/**
 * The stream the feed reads, playing above the Activity (operator, 2026-10-13: "have a shortcut button to open that
 * channel ... or maybe inside Nova itself"). YouTube's privacy-enhanced player, muted to start; mute / unmute talks to
 * it over YouTube's IFrame API. Pop out opens it in a window of its own, Open on YouTube in the browser, and close
 * hides it for this window until Watch live. YouTube asks the desk's network to sign in before it plays ("confirm
 * you're not a bot"): on the desktop, Sign in to YouTube opens Google's own page in a window of its own, and the player
 * reloads when it closes (electron/streamPlayer.mjs). Nothing here reads or trades anything.
 */
import { useEffect, useRef, useState } from 'react';
import { tipProps } from '../ux/hoverTip';
import {
  FT_STREAM_CLOSE,
  FT_STREAM_LIVE,
  FT_STREAM_MUTE,
  FT_STREAM_MUTED,
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
  live: boolean;
}

export function StreamPlayer({ videoId, title, live }: Props) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [muted, setMuted] = useState(true);
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
  const toggleSound = () => {
    frame.current?.contentWindow?.postMessage(playerCommand(muted ? 'unMute' : 'mute'), '*');
    setMuted(!muted);
  };
  return (
    <section className="ft-card ft-stream" aria-label={FT_STREAM_TITLE} data-testid="ft-stream">
      <div className="ft-stream__screen">
        <iframe key={load} ref={frame} className="ft-stream__frame" src={embedUrl(videoId)} title={title ?? FT_STREAM_TITLE}
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen
          referrerPolicy="strict-origin-when-cross-origin" data-testid="ft-stream-frame" />
        {live && <span className="ft-stream__live">{FT_STREAM_LIVE}</span>}
        <div className="ft-stream__tools">
          <button type="button" className="ft-btn ft-btn--overlay" onClick={toggleSound} aria-pressed={!muted}
            {...tipProps(muted ? FT_STREAM_UNMUTE : FT_STREAM_MUTE)} data-testid="ft-stream-sound">
            {muted ? `🔇 ${FT_STREAM_MUTED}` : `🔊 ${FT_STREAM_SOUND_ON}`}
          </button>
          <button type="button" className="ft-btn ft-btn--overlay" onClick={reload} aria-label={FT_STREAM_RELOAD}
            {...tipProps(FT_STREAM_RELOAD)} data-testid="ft-stream-reload">↻</button>
          <button type="button" className="ft-btn ft-btn--overlay" onClick={() => popOutStream(videoId)}
            {...tipProps(FT_STREAM_POP_OUT_TIP)} data-testid="ft-stream-popout">⧉ {FT_STREAM_POP_OUT}</button>
          <button type="button" className="ft-btn ft-btn--overlay" onClick={() => setStreamOpen(false)}
            aria-label={FT_STREAM_CLOSE} {...tipProps(FT_STREAM_CLOSE)} data-testid="ft-stream-close">✕</button>
        </div>
      </div>
      <div className="ft-stream__foot">
        <span className="ft-muted ft-small ft-ellipsis">{title}</span>
        {signIn && (
          <button type="button" className="ft-link ft-small ft-nowrap" {...tipProps(FT_STREAM_SIGN_IN_TIP)}
            onClick={() => void signIn().catch((e: unknown) => console.warn('[nova] YouTube sign-in failed', e))}
            data-testid="ft-stream-sign-in">{FT_STREAM_SIGN_IN}</button>
        )}
        <button type="button" className="ft-link ft-small ft-nowrap" onClick={() => openStreamOnYouTube(videoId)}
          data-testid="ft-stream-youtube">{FT_STREAM_YOUTUBE} ↗</button>
      </div>
    </section>
  );
}
