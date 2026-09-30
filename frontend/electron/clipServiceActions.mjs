/**
 * Share clips (ADR 039): what the desk can ask for (`nova:clips:act`) --
 * start / stop a clip, save the last 5 min, High quality on / off, export,
 * cancel an export, a preview frame, a clip's tracks for the export dialog,
 * delete, show in folder, play. Every request is checked here; an answer is
 * `{ok: true, ...}` or `{ok: false, reason, error}` in the operator's words.
 * Nothing here deletes a screen recording: delete removes the clip's own
 * exports and high-quality files only.
 */
import * as P from './clipPlan.mjs';
import { clipRow, isOpen, latestExport } from './clipManifest.mjs';
import { buildExportPlan, clipTimeline } from './clipExportPlan.mjs';
import { fileSize, freePath, readScreenSegments, removeFile, resolveInside } from './clipStore.mjs';

const fail = (reason, error) => ({ ok: false, reason, error });
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function makeClipActions(ctx) {
  const { store, tabs, hq, exporter, shell, screenView, displayRecording, evaluate, liveFor, append, now, sec } = ctx;
  let seq = 0;
  const newId = (prefix) => `${prefix}-${now()}-${++seq}`;
  const openFor = (symbol) => [...store.clips().values()].find((c) => isOpen(c) && c.symbol === symbol) ?? null;
  const clipOf = (req) => {
    if (typeof req.clip_id === 'string') return store.get(req.clip_id);
    const sym = P.cleanSymbol(req.symbol);
    return sym ? openFor(sym) : null;
  };

  /** The tab's states from the tracker's memory (`historyFor`), as the clip's marks. */
  function appendHistory(id, history) {
    for (const h of history) {
      if (h.shown) {
        append({ event: 'mark', clip_id: id, ts: h.ts, kind: 'shown', detail: { window_id: h.windowId } });
        if (h.geometry) append({ event: 'mark', clip_id: id, ts: h.ts, kind: 'geometry', detail: h.geometry });
      } else {
        append({ event: 'mark', clip_id: id, ts: h.ts, kind: 'hidden', detail: { reason: h.reason, showing: h.showing ?? null } });
      }
    }
  }

  /** The clip with its high-quality files resolved to paths that exist. */
  function withFiles(clip) {
    const dir = ctx.dir();
    const hqFiles = clip.hq
      .map((s) => ({ ...s, file: resolveInside(dir, s.file) }))
      .filter((s) => s.file && fileSize(s.file));
    return { ...clip, hq: hqFiles };
  }

  function screenSegmentsFor(from, to) {
    const v = screenView();
    if (!v?.dir) return [];
    const recording = (v.displays || []).filter((d) => d.recording && d.file).map((d) => d.file);
    return readScreenSegments(v.dir, P.etDates(from * 1000, to * 1000), { now: sec(), recordingFiles: recording });
  }

  function readSettings(clip, raw) {
    const s = raw && typeof raw === 'object' ? raw : {};
    const start = num(s.start_ts) ?? clip.startedTs;
    const end = num(s.end_ts) ?? clip.endedTs ?? sec();
    const picture = P.CLIP_PICTURES.includes(s.picture) ? s.picture : 'trader_tab';
    const pick = (list) => (Array.isArray(list) ? [...new Set(list.filter((id) => P.CLIP_PANELS.includes(id)))] : []);
    return { start_ts: start, end_ts: end, picture, panels: pick(s.panels), blur: pick(s.blur), cut_hidden: s.cut_hidden !== false };
  }

  const actions = {
    start(req) {
      const symbol = P.cleanSymbol(req.symbol);
      if (!symbol) return fail('CLIP_INVALID', 'No symbol to record.');
      const existing = openFor(symbol);
      if (existing) return { ok: true, clip_id: existing.id, already: true };
      const st = tabs.stateFor(symbol, null);
      if (!st.shown && st.reason === 'not_open') {
        return fail('CLIP_NO_TAB', `Open ${symbol}'s Trader tab first: a clip records the tab.`);
      }
      let wantHq = req.hq === true;
      const screenOk = displayRecording(st.geometry?.display_id ?? null);
      const forced = !wantHq && st.shown && screenOk === false;
      if (forced) wantHq = true;
      if (wantHq && hq.count() >= P.CLIP_HQ_MAX_CONCURRENT) {
        return forced
          ? fail('CLIP_NO_PICTURE', 'The screen recording is not seeing that monitor, and both high-quality captures are in use: stop one first.')
          : fail('CLIP_HQ_FULL', 'Both high-quality captures are in use: stop one, or record this clip as a cut.');
      }
      const id = newId('clip');
      const t = sec();
      const origin = ['button', 'symbol_menu', 'hotkey'].includes(req.origin) ? req.origin : 'button';
      append({ event: 'open', clip_id: id, started_ts: t, symbol, origin, picture: 'trader_tab', hq: wantHq });
      // Where the tab was before the press, from the tracker's memory: the export's start can move back that far.
      appendHistory(id, tabs.historyFor(symbol, t - P.CLIP_TAB_HISTORY_SEC).filter((h) => h.ts < t));
      liveFor(id).windowId = st.windowId ?? null;
      evaluate(store.get(id), t);
      return { ok: true, clip_id: id, hq: wantHq, forced };
    },

    stop(req) {
      const clip = clipOf(req);
      if (!clip || !isOpen(clip)) return fail('CLIP_NOT_OPEN', 'That clip is not recording.');
      if (clip.hqWanted) append({ event: 'set', clip_id: clip.id, hq: false, reason: 'clip_closed' });
      hq.stop(clip.id, 'clip_closed');
      append({ event: 'close', clip_id: clip.id, ended_ts: sec(), reason: 'operator' });
      return { ok: true, clip: clipRow(store.get(clip.id), sec()) };
    },

    save_last(req) {
      const symbol = P.cleanSymbol(req.symbol);
      if (!symbol) return fail('CLIP_INVALID', 'No symbol to save.');
      const seconds = Math.min(P.CLIP_TAB_HISTORY_SEC, Math.max(10, num(req.seconds) ?? P.CLIP_LAST_N_SEC));
      const t = sec();
      const from = t - seconds;
      const history = tabs.historyFor(symbol, from);
      if (!history.some((h) => h.shown)) {
        return fail('CLIP_NOT_ON_SCREEN', `${symbol}'s Trader tab has not been on screen in the last ${Math.round(seconds / 60)} min.`);
      }
      const id = newId('clip');
      append({ event: 'open', clip_id: id, started_ts: from, symbol, origin: 'last_n', picture: 'trader_tab', hq: false });
      appendHistory(id, history);
      append({ event: 'close', clip_id: id, ended_ts: t, reason: 'operator' });
      return { ok: true, clip: clipRow(store.get(id), t) };
    },

    set_hq(req) {
      const clip = clipOf(req);
      if (!clip || !isOpen(clip)) return fail('CLIP_NOT_OPEN', 'That clip is not recording.');
      const on = req.on === true;
      if (on === clip.hqWanted) return { ok: true };
      if (on && !hq.active(clip.id) && hq.count() >= P.CLIP_HQ_MAX_CONCURRENT) {
        return fail('CLIP_HQ_FULL', 'Both high-quality captures are in use: stop one first.');
      }
      append({ event: 'set', clip_id: clip.id, hq: on, reason: 'operator' });
      if (!on) hq.stop(clip.id, 'operator');
      Object.assign(liveFor(clip.id), { hqFailures: 0, hqRetryAt: 0, hqLost: false, hqError: null });
      evaluate(store.get(clip.id));
      return { ok: true };
    },

    detail(req) {
      const clip = clipOf(req);
      if (!clip || clip.deleted) return fail('CLIP_UNKNOWN', 'That clip is not on file.');
      const t = sec();
      const end = clip.endedTs ?? t;
      const from = num(req.from_ts) ?? clip.startedTs - 120;
      const to = Math.min(t, num(req.to_ts) ?? end + 120);
      const segs = screenSegmentsFor(from, to);
      return {
        ok: true,
        clip: clipRow(clip, t),
        from_ts: from,
        to_ts: to,
        timeline: clipTimeline({ clip: withFiles(clip), screenSegments: segs, from, to, now: t }),
        out_path: latestExport(clip)?.file ? resolveInside(ctx.dir(), latestExport(clip).file) : null,
      };
    },

    /** The export a request would make, without making it: the dialog's output line. */
    plan(req) {
      const clip = clipOf(req);
      if (!clip || clip.deleted) return fail('CLIP_UNKNOWN', 'That clip is not on file.');
      const settings = readSettings(clip, req.settings);
      const plan = buildExportPlan({
        clip: withFiles(clip),
        settings,
        screenSegments: screenSegmentsFor(settings.start_ts, settings.end_ts),
        now: sec(),
      });
      if (plan.error) return fail('CLIP_NOTHING_TO_EXPORT', `Nothing to export: ${plan.error}.`);
      return { ok: true, out: plan.out, duration: plan.duration, counts: plan.counts, pieces: plan.pieces.length };
    },

    export(req) {
      const clip = clipOf(req);
      if (!clip || clip.deleted) return fail('CLIP_UNKNOWN', 'That clip is not on file.');
      if (isOpen(clip)) return fail('CLIP_OPEN', 'Stop the clip first, then export it.');
      const settings = readSettings(clip, req.settings);
      const t = sec();
      const plan = buildExportPlan({
        clip: withFiles(clip),
        settings,
        screenSegments: screenSegmentsFor(settings.start_ts, settings.end_ts),
        now: t,
      });
      if (plan.error) return fail('CLIP_NOTHING_TO_EXPORT', `Nothing to export: ${plan.error}.`);
      const where = freePath(ctx.dir(), (n) => P.exportRelPath(settings.start_ts * 1000, clip.symbol, n));
      const exportId = newId('ex');
      append({ event: 'export', clip_id: clip.id, export_id: exportId, state: 'queued', file: where.rel, settings: { ...settings, counts: plan.counts, out: plan.out } });
      exporter.enqueue({
        id: exportId,
        clipId: clip.id,
        exportId,
        pieces: plan.pieces,
        outSpec: plan.out,
        duration: plan.duration,
        outFull: where.full,
        outRel: where.rel,
      });
      return { ok: true, export_id: exportId, file: where.full, out: plan.out, duration: plan.duration, counts: plan.counts };
    },

    cancel_export(req) {
      const ok = exporter.cancel(String(req.export_id ?? ''));
      return ok ? { ok: true } : fail('CLIP_EXPORT_UNKNOWN', 'That export is not running.');
    },

    async preview(req) {
      const clip = clipOf(req);
      if (!clip || clip.deleted) return fail('CLIP_UNKNOWN', 'That clip is not on file.');
      const ts = num(req.ts) ?? clip.startedTs;
      const settings = readSettings(clip, { ...req, start_ts: ts, end_ts: ts + 0.05, cut_hidden: false });
      const plan = buildExportPlan({ clip: withFiles(clip), settings, screenSegments: screenSegmentsFor(ts - 1, ts + 1), now: sec() });
      if (plan.error) return fail('CLIP_NO_FRAME', `No picture at that moment: ${plan.error}.`);
      const piece = plan.pieces[0];
      const k = Math.min(1, P.CLIP_PREVIEW_MAX_WIDTH / plan.out.width);
      const out = { width: Math.max(2, Math.round(plan.out.width * k)), height: Math.max(2, Math.round(plan.out.height * k)) };
      const res = await exporter.preview({ file: piece.file, t: piece.t0, crop: piece.crop, out, blur: piece.blur, window: piece.window });
      if (!res.ok) return fail('CLIP_NO_FRAME', res.error);
      const b64 = Buffer.from(res.bytes).toString('base64');
      return { ok: true, data_url: `data:image/jpeg;base64,${b64}`, width: out.width, height: out.height, source: piece.kind, out: plan.out };
    },

    delete(req) {
      const clip = clipOf(req);
      if (!clip || clip.deleted) return fail('CLIP_UNKNOWN', 'That clip is not on file.');
      if (isOpen(clip)) return fail('CLIP_OPEN', 'Stop the clip first.');
      if (exporter.running()?.clipId === clip.id || exporter.queued().some((j) => j.clipId === clip.id)) {
        return fail('CLIP_EXPORTING', 'Cancel its export first.');
      }
      const dir = ctx.dir();
      const files = [...[...clip.exports.values()].map((e) => e.file), ...clip.hq.map((s) => s.file)].filter(Boolean);
      const errors = files.map((rel) => removeFile(resolveInside(dir, rel))).filter(Boolean);
      if (errors.length) return fail('CLIP_DELETE_FAILED', `Not every file could be deleted: ${errors[0]}`);
      append({ event: 'delete', clip_id: clip.id, files });
      return { ok: true, files: files.length };
    },

    show(req) {
      const full = exportedFile(req);
      if (!full) return fail('CLIP_NO_FILE', 'This clip has no exported file yet.');
      shell.showItemInFolder(full);
      return { ok: true };
    },

    async play(req) {
      const full = exportedFile(req);
      if (!full) return fail('CLIP_NO_FILE', 'This clip has no exported file yet.');
      const error = await shell.openPath(full);
      return error ? fail('CLIP_OPEN_FAILED', error) : { ok: true };
    },
  };

  function exportedFile(req) {
    const clip = clipOf(req);
    const e = clip ? [...clip.exports.values()].filter((x) => x.state === 'done').sort((a, b) => b.ts - a.ts)[0] : null;
    const full = e?.file ? resolveInside(ctx.dir(), e.file) : null;
    return full && fileSize(full) ? full : null;
  }

  return {
    async act(request) {
      const req = request && typeof request === 'object' ? request : {};
      const fn = Object.prototype.hasOwnProperty.call(actions, req.action) ? actions[req.action] : null;
      if (!fn) return fail('CLIP_INVALID', `Unknown clip action: ${String(req.action ?? '')}`);
      try {
        return await fn(req);
      } catch (err) {
        return fail('CLIP_ERROR', err instanceof Error ? err.message : String(err));
      } finally {
        ctx.publish();
      }
    },
  };
}
