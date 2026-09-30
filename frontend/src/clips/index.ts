/**
 * Share clips (ADR 039), the feature's barrel: what the rest of the desk may
 * use -- the red ● Record button for a Trader tab strip, the tab reporter and
 * the frame for the Trader view, the header's CLIP chips / toasts / export
 * dialog, the Records list, and the store's requests.
 */
import './clips.css';

export { RecordButton } from './RecordButton';
export { useClipTabReport } from './clipTabReport';
export { ClipFrame } from './ClipFrame';
export { ClipChips } from './ClipChips';
export { ClipToasts } from './ClipToasts';
export { ClipExportHost } from './ClipExportDialog';
export { ClipsList } from './ClipsList';
export { ClipMenuRows } from './ClipMenuRows';
export { runClipHotkey } from './clipHotkeys';
export { actClip, openClipExport, pushClipToast, takeClipsListRequest, useClips } from './clipsStore';
export { openClipFor } from './clipModel';
export { CLIP_RECORDS_TAB_CLIPS, CLIP_RECORDS_TAB_SESSIONS } from './clipsConstants';
