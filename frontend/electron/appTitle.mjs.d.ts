export function withReleaseTag(base: string, releaseTag: string): string;
export function formatScannerWindowTitle(releaseTag: string): string;
export function formatTraderDocumentTitle(symbol: string, releaseTag: string): string;
export function formatElectronTraderTitle(symbol: string, releaseTag: string): string;
export function novaWindowTitle(opts?: {
  traderActive?: boolean;
  traderSymbol?: string | null;
  releaseTag?: string;
}): string;
export function resolveNovaTitleDesk(opts?: {
  sampleMode?: boolean;
  sampleSymbol?: string | null;
  liveTraderActive?: boolean;
  liveTraderSymbol?: string | null;
}): { traderActive: boolean; traderSymbol: string };
export function injectNovaTitle(html: string, releaseTag: string): string;
