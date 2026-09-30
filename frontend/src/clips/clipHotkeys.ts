/**
 * The two Nova Actions of share clips (ADR 039): "Start / stop clip" and
 * "Save the last 5 min", on the active Trader tab. They ship unbound; the
 * operator binds them in Settings › Hotkeys beside the trading keys. Neither
 * places, stages or cancels anything -- runNovaAction hands them here before
 * any gate or order path.
 */
import { openClipFor } from './clipModel';
import { CLIP_NEED_DESKTOP } from './clipsConstants';
import { actClip, clipsBridge, getClipsView, pushClipToast } from './clipsStore';

export async function runClipHotkey(kind: 'clip_toggle' | 'clip_save_last', symbol: string | null): Promise<{ ok: boolean; text: string }> {
  if (!symbol) return { ok: false, text: 'No Trader tab is active: a clip records the tab.' };
  if (!clipsBridge()) return { ok: false, text: CLIP_NEED_DESKTOP };
  if (kind === 'clip_save_last') {
    const res = await actClip({ action: 'save_last', symbol, seconds: getClipsView()?.lastNSec });
    const clipId = (res.clip as { clip_id?: string } | undefined)?.clip_id;
    if (res.ok && clipId) pushClipToast({ kind: 'last', clipId, clip: null, text: symbol });
    return { ok: res.ok, text: res.ok ? `Saved the last 5 min of ${symbol} as a clip` : res.error ?? 'Nothing was saved.' };
  }
  const open = openClipFor(getClipsView(), symbol);
  if (open) {
    const res = await actClip({ action: 'stop', clip_id: open.clipId });
    if (res.ok) pushClipToast({ kind: 'saved', clipId: open.clipId, clip: null, text: symbol });
    return { ok: res.ok, text: res.ok ? `Saved the clip of ${symbol}` : res.error ?? 'The clip did not stop.' };
  }
  const res = await actClip({ action: 'start', symbol, hq: false, origin: 'hotkey' });
  return { ok: res.ok, text: res.ok ? `Recording a clip of ${symbol}` : res.error ?? 'The clip did not start.' };
}
