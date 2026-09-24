export function withReleaseTag(base: string, releaseTag: string): string;
export function formatScannerWindowTitle(releaseTag: string): string;
export function formatTraderDocumentTitle(symbol: string, releaseTag: string): string;
export function formatElectronTraderTitle(symbol: string, releaseTag: string): string;
export function withRecording(base: string, recordingSymbol: string | null | undefined): string;
export function isOlderTag(tag: string | null | undefined, than: string | null | undefined): boolean;
export function withBackendTag(base: string, backendTag: string | null | undefined, releaseTag: string): string;
export function novaWindowTitle(opts?: {
  traderActive?: boolean;
  traderSymbol?: string | null;
  releaseTag?: string;
  recordingSymbol?: string | null;
  backendTag?: string | null;
}): string;
export function resolveNovaTitleDesk(opts?: {
  sampleMode?: boolean;
  sampleSymbol?: string | null;
  liveTraderActive?: boolean;
  liveTraderSymbol?: string | null;
}): { traderActive: boolean; traderSymbol: string };
export function injectNovaTitle(html: string, releaseTag: string): string;
