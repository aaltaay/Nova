/**
 * The export dialog (ADR 039, mockup v1 board 4): a preview of the frame
 * under the playhead, the picture (the Trader tab with the header out by
 * default; panels, the whole window or the monitor say what they show), the
 * panels to blur (the ones with the operator's size and P&L, on by default),
 * the trim timeline, the output line and X's length hint. Export queues it;
 * Records › Video clips shows the progress. Nothing leaves the PC.
 */
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constantGroups/chart_api';
import { clockLabel, etClock, etDate } from './clipModel';
import { ClipTimeline, type Moment, type TimelineTracks } from './ClipTimeline';
import {
  CLIP_CANCEL,
  CLIP_EXPORT_BUTTON,
  CLIP_EXPORT_CHART_POSITION,
  CLIP_EXPORT_IN_PICTURE,
  CLIP_EXPORT_NOTE,
  CLIP_EXPORT_OUTPUT,
  CLIP_EXPORT_PICTURE,
  CLIP_EXPORT_TITLE,
  CLIP_PANEL_LABELS,
  CLIP_PICTURE_OPTIONS,
  CLIP_PRIVATE_PANELS,
  CLIP_TIMELINE_PAD_SEC,
  type ClipPanelId,
  type ClipPicture,
} from './clipsConstants';
import { actClip, closeClipExport, getClipsVersion, getExportDialogClip, subscribeClips, useClips } from './clipsStore';
import { coverLine, defaultSettings, outputParts, settingsWire, sourceLine, xWarning, type ExportPlanView, type ExportSettings } from './clipExportModel';

type Detail = { from: number; to: number; tracks: TimelineTracks; outPath: string | null };

async function readMoments(symbol: string, date: string, from: number, to: number): Promise<Moment[]> {
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/stock-read/${encodeURIComponent(symbol)}/decisions?date=${date}`);
    if (!res.ok) return [];
    const body = (await res.json()) as { events?: { ts?: number; event?: string; title?: string }[] };
    const out: Moment[] = [];
    for (const e of body.events ?? []) {
      if (typeof e.ts !== 'number' || e.ts < from || e.ts > to) continue;
      const title = String(e.title ?? '');
      if (e.event === 'triggered') out.push({ ts: e.ts, label: 'trigger', tone: 'go' });
      else if (e.event === 'scored' && /target/i.test(title)) out.push({ ts: e.ts, label: 'target', tone: 'target' });
      else if (e.event === 'scored' && /stop/i.test(title)) out.push({ ts: e.ts, label: 'stop', tone: 'stop' });
    }
    return out.slice(0, 8);
  } catch {
    return []; // the moments are a guide; a failed read leaves the track empty
  }
}

function Dialog({ clipId }: { clipId: string }) {
  const { view } = useClips();
  const row = view?.clips.find((c) => c.clipId === clipId) ?? null;
  const [settings, setSettings] = useState<ExportSettings | null>(() => (row ? defaultSettings(row) : null));
  const [detail, setDetail] = useState<Detail | null>(null);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [plan, setPlan] = useState<ExportPlanView | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ url: string; source: string } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (row && !settings) setSettings(defaultSettings(row));
  }, [row, settings]);

  useEffect(() => {
    if (!row) return;
    let live = true;
    const end = row.endedTs ?? row.startedTs + row.lengthSec;
    void actClip({ action: 'detail', clip_id: clipId, from_ts: row.startedTs - CLIP_TIMELINE_PAD_SEC, to_ts: end + CLIP_TIMELINE_PAD_SEC }).then((res) => {
      if (!live || !res.ok) return;
      setDetail({ from: res.from_ts as number, to: res.to_ts as number, tracks: res.timeline as TimelineTracks, outPath: (res.out_path as string | null) ?? null });
      void readMoments(row.symbol, etDate(row.startedTs), res.from_ts as number, res.to_ts as number).then((m) => live && setMoments(m));
    });
    setPlayhead(Math.round(row.startedTs + Math.min(6, row.lengthSec / 2)));
    return () => {
      live = false;
    };
    // The clip's identity decides the tracks; its live row changes every second while exporting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipId, row?.startedTs]);

  const wire = useMemo(() => (settings ? settingsWire(settings) : null), [settings]);
  useEffect(() => {
    if (!wire) return undefined;
    const id = window.setTimeout(() => {
      void actClip({ action: 'plan', clip_id: clipId, settings: wire }).then((res) => {
        if (res.ok) {
          setPlan({ out: res.out as ExportPlanView['out'], duration: res.duration as number, counts: res.counts as ExportPlanView['counts'] });
          setPlanError(null);
        } else {
          setPlan(null);
          setPlanError(res.error ?? 'Nothing to export.');
        }
      });
    }, 250);
    return () => window.clearTimeout(id);
  }, [wire, clipId]);

  useEffect(() => {
    if (!wire || playhead === null) return undefined;
    const id = window.setTimeout(() => {
      void actClip({ action: 'preview', clip_id: clipId, ts: playhead, picture: wire.picture, panels: wire.panels, blur: wire.blur }).then((res) => {
        if (res.ok) {
          setPreview({ url: String(res.data_url), source: String(res.source) });
          setPreviewError(null);
        } else setPreviewError(res.error ?? 'No picture at that moment.');
      });
    }, 300);
    return () => window.clearTimeout(id);
  }, [wire?.picture, wire?.panels.join(','), wire?.blur.join(','), playhead, clipId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeClipExport();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!row || !settings) return null;
  const set = (patch: Partial<ExportSettings>) => setSettings({ ...settings, ...patch });
  const togglePanel = (key: 'panels' | 'blur', id: ClipPanelId) => {
    const list = settings[key];
    set({ [key]: list.includes(id) ? list.filter((x) => x !== id) : [...list, id] } as Partial<ExportSettings>);
  };
  const exportNow = async () => {
    setBusy(true);
    setError(null);
    const res = await actClip({ action: 'export', clip_id: clipId, settings: settingsWire(settings) });
    setBusy(false);
    if (!res.ok) {
      setError(res.error ?? 'The export did not start.');
      return;
    }
    closeClipExport();
  };
  const hidden = detail?.tracks.hidden.filter((h) => h.end > settings.startTs && h.start < settings.endTs) ?? [];
  const warn = plan ? xWarning(plan.duration) : null;
  const pictureWarn = CLIP_PICTURE_OPTIONS[settings.picture].warn;
  const chartsIn = settings.picture !== 'panels' || settings.panels.includes('charts');
  const cover = plan ? coverLine(plan, settings.picture) : null;

  return createPortal(
    <div className="clip-export-backdrop" data-testid="clip-export">
      <div className="clip-export" role="dialog" aria-modal="true" aria-labelledby="clip-export-title">
        <header className="clip-export__head">
          <h3 id="clip-export-title">{CLIP_EXPORT_TITLE} · {row.symbol}</h3>
          <span className="clip-export__muted">{etDate(row.startedTs)} · {etClock(settings.startTs)} → {etClock(settings.endTs)} ET · {clockLabel(settings.endTs - settings.startTs)}</span>
          <button type="button" className="clip-export__close" aria-label="Close" onClick={closeClipExport}><X size={16} aria-hidden="true" /></button>
        </header>
        <div className="clip-export__body">
          <div className="clip-export__preview" data-testid="clip-export-preview">
            {preview ? <img src={preview.url} alt={`The clip's picture at ${playhead ? etClock(playhead) : ''}`} /> : <div className="clip-export__nopreview">{previewError ?? 'Drawing the frame…'}</div>}
            {preview && playhead ? <span className="clip-export__tag">{etClock(playhead)} · {preview.source === 'hq' ? 'high quality' : 'screen recording'}</span> : null}
          </div>
          <div className="clip-export__side">
            <div className="clip-export__label">{CLIP_EXPORT_PICTURE}</div>
            {(Object.keys(CLIP_PICTURE_OPTIONS) as ClipPicture[]).map((p) => {
              const o = CLIP_PICTURE_OPTIONS[p];
              return (
                <label key={p} className={`clip-radio${settings.picture === p ? ' is-on' : ''}`}>
                  <input type="radio" name="clip-picture" checked={settings.picture === p} onChange={() => set({ picture: p })} />
                  <span>
                    <b>{p === 'trader_tab' ? `${row.symbol}'s Trader tab` : o.label}</b>
                    {o.hint ? <small>{o.hint}</small> : null}
                    {o.warn ? <small className="clip-warn-text">{o.warn}</small> : null}
                  </span>
                </label>
              );
            })}
            {settings.picture === 'panels' ? (
              <div className="clip-chips-pick">
                {(Object.keys(CLIP_PANEL_LABELS) as ClipPanelId[]).map((id) => (
                  <button key={id} type="button" className={`clip-pick${settings.panels.includes(id) ? ' is-on' : ''}`} aria-pressed={settings.panels.includes(id)} onClick={() => togglePanel('panels', id)}>
                    {CLIP_PANEL_LABELS[id]}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="clip-export__label">{CLIP_EXPORT_IN_PICTURE}</div>
            {pictureWarn ? <p className="clip-export__line clip-warn-text">! {pictureWarn}</p> : <p className="clip-export__line"><span className="clip-ok">✓</span> No account id, Day&apos;s P&amp;L or TAV: the header is out.</p>}
            <p className="clip-export__line">Your size and P&amp;L show on these; blurred ones are unreadable in the export:</p>
            <div className="clip-chips-pick">
              {CLIP_PRIVATE_PANELS.map((id) => (
                <label key={id} className={`clip-check${settings.blur.includes(id) ? ' is-on' : ''}`}>
                  <input type="checkbox" checked={settings.blur.includes(id)} onChange={() => togglePanel('blur', id)} />
                  <span>Blur {CLIP_PANEL_LABELS[id].toLowerCase()}</span>
                </label>
              ))}
            </div>
            {chartsIn ? <p className="clip-export__line clip-export__muted">{CLIP_EXPORT_CHART_POSITION}</p> : null}
            <div className="clip-export__label">{CLIP_EXPORT_OUTPUT}</div>
            {plan ? (
              <>
                <p className="clip-export__line">{outputParts(plan).join(' · ')}</p>
                <p className="clip-export__line clip-export__muted">{sourceLine(plan)}</p>
                {cover ? <p className="clip-export__line clip-export__muted">{cover}</p> : null}
              </>
            ) : <p className="clip-export__line clip-warn-text">{planError ?? 'Working out the export…'}</p>}
            {detail?.outPath ? <p className="clip-export__line clip-export__muted">Last export: {detail.outPath}</p> : null}
            {warn ? <div className="clip-export__warn">{warn}</div> : null}
          </div>
        </div>
        {detail ? (
          <ClipTimeline
            from={detail.from}
            to={detail.to}
            tracks={detail.tracks}
            moments={moments}
            symbol={row.symbol}
            start={settings.startTs}
            end={settings.endTs}
            playhead={playhead}
            onSelect={(startTs, endTs) => set({ startTs, endTs })}
            onPlayhead={setPlayhead}
          />
        ) : <div className="clip-tl clip-tl--loading">Reading the recordings…</div>}
        <div className="clip-export__cut">
          <label className={`clip-check${settings.cutHidden ? ' is-on' : ''}`}>
            <input type="checkbox" checked={settings.cutHidden} onChange={() => set({ cutHidden: !settings.cutHidden })} />
            <span>
              Cut the stretches the tab showed something else
              {hidden.length ? ` (${hidden.map((h) => `${h.showing ?? 'hidden'} ${etClock(h.start)}–${etClock(h.end)}`).join(', ')})` : ' (none in this stretch)'}
            </span>
          </label>
        </div>
        {error ? <p className="clip-export__error" role="alert">{error}</p> : null}
        <footer className="clip-export__foot">
          <button type="button" className="clip-btn clip-btn--pri" data-testid="clip-export-go" disabled={busy || !plan} data-why={busy ? 'Starting the export…' : !plan ? planError ?? 'Working out the export…' : undefined} onClick={() => void exportNow()}>
            {CLIP_EXPORT_BUTTON}
          </button>
          <button type="button" className="clip-btn" onClick={closeClipExport}>{CLIP_CANCEL}</button>
          <span className="clip-export__note">{CLIP_EXPORT_NOTE}</span>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

/** The one export dialog of the main desk: open for the clip `openClipExport` names. */
export function ClipExportHost() {
  useSyncExternalStore(subscribeClips, getClipsVersion, () => 0);
  const clipId = getExportDialogClip();
  return clipId ? <Dialog key={clipId} clipId={clipId} /> : null;
}
