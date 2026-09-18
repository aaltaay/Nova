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

export function novaWindowTitle({
  traderActive = false,
  traderSymbol = '',
  releaseTag = '',
} = {}) {
  if (traderActive) return formatTraderDocumentTitle(traderSymbol, releaseTag);
  return formatScannerWindowTitle(releaseTag);
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
