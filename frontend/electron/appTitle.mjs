/**
 * OS / document titles. View label stays; public revision is VERSION (vNNN).
 * Electron main and the Vite renderer share this so packaged and electron:dev
 * titles cannot drift.
 */
const TITLE_APP = 'Nova';
const TITLE_SCANNER_VIEW = 'Stock Scanner';
const TITLE_TRADER_VIEW = 'Trader';
/** Matches the existing index.html / StockViewPage scanner title punctuation. */
const TITLE_APP_VIEW_SEP = ' — ';
/** A running Session Record leads the OS title, so the taskbar says so too. */
const TITLE_RECORDING_PREFIX = '● REC';
/** The backend's own revision follows the desk's (operator ask 2026-09-24). */
const TITLE_BACKEND = 'backend';
const TITLE_BACKEND_OLDER = ' (older -- restart it)';
/** Older, and its checkout holds nothing newer: a restart would start the same code again. */
const TITLE_BACKEND_BEHIND = ' (older -- pull master, then restart)';

export function withReleaseTag(base, releaseTag) {
  const tag = String(releaseTag ?? '').trim();
  return tag ? `${base} · ${tag}` : base;
}

export function formatScannerWindowTitle(releaseTag) {
  return withReleaseTag(`${TITLE_APP}${TITLE_APP_VIEW_SEP}${TITLE_SCANNER_VIEW}`, releaseTag);
}

export function formatTraderDocumentTitle(symbol, releaseTag) {
  const sym = String(symbol ?? '').trim();
  const base = sym
    ? `${sym} · ${TITLE_TRADER_VIEW} · ${TITLE_APP}`
    : `${TITLE_TRADER_VIEW} · ${TITLE_APP}`;
  return withReleaseTag(base, releaseTag);
}

export function formatElectronTraderTitle(symbol, releaseTag) {
  const sym = String(symbol ?? '').trim() || TITLE_TRADER_VIEW;
  return withReleaseTag(`${TITLE_APP} -- ${sym}`, releaseTag);
}

function tagNumber(tag) {
  const m = /^v(\d+)$/.exec(String(tag ?? '').trim());
  return m ? Number(m[1]) : null;
}

/** True when `tag` is an older vNNN than `than`; false when either is unknown. */
export function isOlderTag(tag, than) {
  const a = tagNumber(tag);
  const b = tagNumber(than);
  return a != null && b != null && a < b;
}

/**
 * What a backend older than the desk needs. A restart loads whatever its checkout holds
 * (`/api/health` `checkout_tag`), so: 'restart' when the checkout is ahead of it or Nova cannot
 * tell, 'pull' when the checkout holds nothing newer -- a restart would start the same revision
 * again (operator report 2026-09-25) -- and null when the backend is not older.
 */
export function backendRemedy(backendTag, releaseTag, checkoutTag) {
  if (!isOlderTag(backendTag, releaseTag)) return null;
  const checkout = tagNumber(checkoutTag);
  return checkout != null && checkout <= tagNumber(backendTag) ? 'pull' : 'restart';
}

/**
 * "... · backend v1006" -- the revision the local API process runs, read from its /api/health.
 * A backend left running across an update keeps its old code until it restarts, so an older
 * one says so, and says to pull first when a restart alone would load the same code. Unknown
 * (the API not answering, the sample desk) adds nothing.
 */
export function withBackendTag(base, backendTag, releaseTag, checkoutTag = null) {
  const api = String(backendTag ?? '').trim();
  if (!api) return base;
  const remedy = backendRemedy(api, releaseTag, checkoutTag);
  const note = remedy === 'pull' ? TITLE_BACKEND_BEHIND : remedy === 'restart' ? TITLE_BACKEND_OLDER : '';
  return `${base} · ${TITLE_BACKEND} ${api}${note}`;
}

export function withRecording(base, recordingSymbol) {
  const sym = String(recordingSymbol ?? '').trim();
  return sym ? `${TITLE_RECORDING_PREFIX} ${sym}${TITLE_APP_VIEW_SEP}${base}` : base;
}

export function novaWindowTitle({
  traderActive = false,
  traderSymbol = '',
  releaseTag = '',
  recordingSymbol = '',
  backendTag = '',
  checkoutTag = '',
} = {}) {
  const base = traderActive
    ? formatTraderDocumentTitle(traderSymbol, releaseTag)
    : formatScannerWindowTitle(releaseTag);
  return withRecording(withBackendTag(base, backendTag, releaseTag, checkoutTag), recordingSymbol);
}

/** Sample `?view=sample&symbol=` is a Trader desk; live uses the Scanner|Trader switch. */
export function resolveNovaTitleDesk({
  sampleMode = false,
  sampleSymbol = '',
  liveTraderActive = false,
  liveTraderSymbol = '',
} = {}) {
  if (sampleMode) {
    const symbol = String(sampleSymbol ?? '').trim();
    return { traderActive: Boolean(symbol), traderSymbol: symbol };
  }
  return {
    traderActive: Boolean(liveTraderActive),
    traderSymbol: liveTraderSymbol ?? '',
  };
}

export function injectNovaTitle(html, releaseTag) {
  const title = formatScannerWindowTitle(releaseTag);
  return String(html).replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`);
}
