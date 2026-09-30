/**
 * The Record menu (ADR 039, mockup v1 board 1): one menu per symbol with two
 * independent parts -- Market data (the Session Record, unchanged: Level 2 +
 * Time & Sales for Sim, stopping is a hold) and Video clip (a cut from the
 * screen recording, Save the last 5 min, High quality). Every locked control
 * says why (ux/whyTip.ts); a refused request shows its reason in the menu.
 */
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { Disc, History, Square, Video } from 'lucide-react';
import {
  CAPTURE_STOP_HOLD_HINT,
  captureStopHoldLabel,
  getRecordingSymbols,
  getSessionRecordError,
  getSessionRecordVersion,
  HoldToStopButton,
  isTabRecording,
  startTabRecord,
  stopTabRecord,
  subscribeSessionRecord,
} from '../capture';
import { NAV_RAIL_RECORDING_MAX } from '../constantGroups/nav_rail';
import { parseStockViewSymbol } from '../utils/stockViewNav';
import { setNavPage, useWorkspace } from '../workspace';
import { bytesLabel, clockLabel, etClock, videoMenuState } from './clipModel';
import {
  CLIP_HQ,
  CLIP_MD_DESC,
  CLIP_MD_FULL_WHY,
  CLIP_MD_TITLE,
  CLIP_MENU_KEYS,
  CLIP_MENU_TITLE,
  CLIP_NEED_DESKTOP,
  CLIP_PICTURE_LINE,
  CLIP_RECORDS_LINK,
  CLIP_SAVE_LAST,
  CLIP_SAVE_LAST_HINT,
  CLIP_START,
  CLIP_START_BOTH,
  CLIP_START_BOTH_HINT,
  CLIP_START_CLIP,
  CLIP_STOP_CLIP,
  CLIP_VIDEO_DESC,
  CLIP_VIDEO_TITLE,
} from './clipsConstants';
import { actClip, pushClipToast, requestClipsList, useClips } from './clipsStore';
import type { ClipRowView } from './clipsView';

const MENU_W = 400;

export function RecordMenu({ symbol, anchor, onClose }: { symbol: string; anchor: HTMLElement; onClose: () => void }) {
  const { desktop, view } = useClips();
  useSyncExternalStore(subscribeSessionRecord, getSessionRecordVersion, () => 0);
  const workspace = useWorkspace();
  const menuRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wantHq, setWantHq] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [now, setNow] = useState(() => Date.now() / 1000);

  useLayoutEffect(() => {
    const r = anchor.getBoundingClientRect();
    const left = Math.max(8, Math.min(r.right - MENU_W, window.innerWidth - MENU_W - 8));
    setPos({ top: r.bottom + 6, left });
  }, [anchor]);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node) && !anchor.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const tick = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.clearInterval(tick);
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [anchor, onClose]);

  const recording = isTabRecording(symbol);
  const mdCount = getRecordingSymbols().length;
  const mdFull = !recording && mdCount >= NAV_RAIL_RECORDING_MAX;
  const mdError = getSessionRecordError(symbol);
  const vs = videoMenuState({ desktop, view, symbol, busy });
  const open = vs.open;
  const hqOn = open ? Boolean(open.hq) : wantHq || vs.noScreen;
  const detached = parseStockViewSymbol() != null;

  /** Runs an action; a start or stop that worked closes the menu, so it never sits over Level 2 (the chips say what runs). */
  const run = async (fn: () => Promise<string | null>, closeWhenDone = false) => {
    setBusy(true);
    setError(null);
    const err = await fn();
    setBusy(false);
    if (err) setError(err);
    else if (closeWhenDone) onClose();
  };
  const startMd = () => run(async () => startTabRecord(symbol), true);
  const stopMd = () => run(async () => stopTabRecord(symbol), true);
  const startClip = () => run(async () => {
    const res = await actClip({ action: 'start', symbol, hq: hqOn, origin: 'button' });
    return res.ok ? null : res.error ?? 'The clip did not start.';
  }, true);
  const stopClip = () => run(async () => {
    if (!open) return null;
    const res = await actClip({ action: 'stop', clip_id: open.clipId });
    if (!res.ok) return res.error ?? 'The clip did not stop.';
    const clip = res.clip as ClipRowView | undefined;
    pushClipToast({ kind: 'saved', clipId: open.clipId, clip: null, text: clip ? `${symbol} ${clockLabel(clip.lengthSec)}` : symbol });
    onClose();
    return null;
  });
  const saveLast = () => run(async () => {
    const res = await actClip({ action: 'save_last', symbol, seconds: view?.lastNSec });
    if (!res.ok) return res.error ?? 'Nothing was saved.';
    const clip = res.clip as { clip_id?: string } | undefined;
    if (clip?.clip_id) pushClipToast({ kind: 'last', clipId: clip.clip_id, clip: null, text: symbol });
    onClose();
    return null;
  });
  const toggleHq = () => {
    if (!open) {
      setWantHq((v) => !v);
      return;
    }
    void run(async () => {
      const res = await actClip({ action: 'set_hq', clip_id: open.clipId, on: !open.hq });
      return res.ok ? null : res.error ?? 'High quality did not change.';
    });
  };
  const startBoth = () => run(async () => {
    const md = await startTabRecord(symbol);
    const res = await actClip({ action: 'start', symbol, hq: hqOn, origin: 'button' });
    return md ?? (res.ok ? null : res.error ?? 'The clip did not start.');
  }, true);
  const goRecords = () => {
    requestClipsList();
    workspace.showScannerView();
    setNavPage('records');
    onClose();
  };

  const mdHint = recording ? `Recording · ${mdCount} of ${NAV_RAIL_RECORDING_MAX} in use.` : `Uses a Level 2 line · ${mdCount} of ${NAV_RAIL_RECORDING_MAX} in use.`;
  const disk = view?.disk.freeBytes !== null && view?.disk.freeBytes !== undefined ? ` · ${view.dir.slice(0, 2)} ${bytesLabel(view.disk.freeBytes)} free` : '';
  const hqEndsIn = open?.hq?.endsAt ? clockLabel(open.hq.endsAt - now) : null;

  return createPortal(
    <div ref={menuRef} className="clip-menu" role="dialog" aria-label={`${CLIP_MENU_TITLE} ${symbol}`} data-testid="clip-menu" style={{ top: pos.top, left: pos.left, width: MENU_W }}>
      <div className="clip-menu__head">
        <span className="clip-menu__title">{CLIP_MENU_TITLE}</span>
        <b>{symbol}</b>
        <span className="clip-menu__keys">{CLIP_MENU_KEYS}</span>
      </div>

      <section className="clip-menu__part" data-testid="clip-menu-md">
        <div className="clip-menu__row">
          <span className="clip-menu__icon clip-menu__icon--md" aria-hidden="true"><Disc size={13} /></span>
          <span className="clip-menu__name">{CLIP_MD_TITLE}</span>
          {recording ? (
            <HoldToStopButton
              testId="clip-menu-md-stop"
              className="clip-btn clip-btn--sm"
              label={captureStopHoldLabel(symbol)}
              disabled={busy}
              why={busy ? 'Working on it…' : null}
              onConfirm={() => void stopMd()}
            >
              <Square size={10} fill="currentColor" aria-hidden="true" /> Hold to stop
            </HoldToStopButton>
          ) : (
            <button type="button" className="clip-btn clip-btn--rec clip-btn--sm" data-testid="clip-menu-md-start"
              disabled={busy || mdFull} data-why={mdFull ? CLIP_MD_FULL_WHY : busy ? 'Working on it…' : undefined} onClick={() => void startMd()}>
              {CLIP_START}
            </button>
          )}
        </div>
        <p className="clip-menu__desc">{CLIP_MD_DESC} {mdHint}{recording ? ` ${CAPTURE_STOP_HOLD_HINT}` : ''}</p>
        {mdFull ? <p className="clip-menu__why">{CLIP_MD_FULL_WHY}</p> : null}
        {mdError ? <p className="clip-menu__why clip-menu__why--bad">{mdError}</p> : null}
      </section>

      <section className="clip-menu__part" data-testid="clip-menu-video">
        <div className="clip-menu__row">
          <span className="clip-menu__icon clip-menu__icon--video" aria-hidden="true"><Video size={13} /></span>
          <span className="clip-menu__name">{CLIP_VIDEO_TITLE}</span>
          {open ? (
            <>
              <span className="clip-menu__run" data-testid="clip-menu-running"><i aria-hidden="true" />{clockLabel(now - open.startedTs)}</span>
              <button type="button" className="clip-btn clip-btn--sm" data-testid="clip-menu-stop" disabled={busy} data-why={busy ? 'Working on it…' : undefined} onClick={() => void stopClip()}>
                <Square size={10} fill="currentColor" aria-hidden="true" /> {CLIP_STOP_CLIP}
              </button>
            </>
          ) : (
            <button type="button" className="clip-btn clip-btn--rec clip-btn--sm" data-testid="clip-menu-start" disabled={!vs.canStart} data-why={vs.startWhy ?? undefined} onClick={() => void startClip()}>
              ● {CLIP_START_CLIP}
            </button>
          )}
        </div>
        {!desktop ? (
          <p className="clip-menu__why clip-menu__why--bad">{CLIP_NEED_DESKTOP}</p>
        ) : (
          <>
            <p className={`clip-menu__desc${vs.noScreen ? ' clip-menu__desc--warn' : ''}`}>
              {open
                ? open.hq
                  ? `Recording since ${etClock(open.startedTs)}. High quality ${hqEndsIn ?? ''} left, then the clip goes on as a cut.`
                  : `Recording since ${etClock(open.startedTs)}, cut from the screen recording.`
                : vs.noScreen
                  ? 'The screen recording is not seeing this monitor, so a cut would have no picture. High quality records this window on its own.'
                  : CLIP_VIDEO_DESC}
            </p>
            {!vs.noScreen ? (
              <div className="clip-menu__line">
                <button type="button" className="clip-btn clip-btn--ghost clip-btn--sm" data-testid="clip-menu-save-last"
                  disabled={busy || !view} data-why={busy ? 'Working on it…' : !view ? 'The desktop app has not answered yet' : undefined} onClick={() => void saveLast()}>
                  <History size={11} aria-hidden="true" /> {CLIP_SAVE_LAST}
                </button>
                <span className="clip-menu__muted">{CLIP_SAVE_LAST_HINT}</span>
              </div>
            ) : null}
            <div className="clip-menu__line">
              <label className={`clip-check${hqOn ? ' is-on' : ''}${vs.hqLocked ? ' is-locked' : ''}`} data-testid="clip-menu-hq">
                <input type="checkbox" checked={hqOn} disabled={vs.hqLocked} data-why={vs.hqWhy ?? undefined} onChange={toggleHq} />
                <span>{CLIP_HQ}</span>
              </label>
              <span className="clip-menu__muted">{vs.hqNote}</span>
            </div>
            {vs.hqLocked && vs.hqWhy && !vs.noScreen ? <p className="clip-menu__why">{vs.hqWhy}</p> : null}
          </>
        )}
      </section>

      {!recording && !open && desktop ? (
        <section className="clip-menu__part clip-menu__part--row">
          <button type="button" className="clip-btn clip-btn--rec clip-btn--sm" data-testid="clip-menu-both"
            disabled={busy || mdFull || !vs.canStart} data-why={mdFull ? CLIP_MD_FULL_WHY : vs.startWhy ?? (busy ? 'Working on it…' : undefined)} onClick={() => void startBoth()}>
            ● {CLIP_START_BOTH}
          </button>
          <span className="clip-menu__muted">{CLIP_START_BOTH_HINT}</span>
        </section>
      ) : null}

      {error ? <p className="clip-menu__why clip-menu__why--bad" role="alert" data-testid="clip-menu-error">{error}</p> : null}

      <footer className="clip-menu__foot">
        In the picture: <b>{symbol}&apos;s Trader tab</b>, {CLIP_PICTURE_LINE}
        <br />
        Clips:{' '}
        {detached ? <span>{CLIP_RECORDS_LINK}</span> : (
          <button type="button" className="clip-link" data-testid="clip-menu-records" onClick={goRecords}>{CLIP_RECORDS_LINK}</button>
        )}
        {disk}
      </footer>
    </div>,
    document.body,
  );
}
