export function formatReleaseTag(count: number): string;
export function releaseTagFromText(text: string): string;
export function loadNovaReleaseTag(opts?: {
  appVersion?: string;
  isPackaged?: boolean;
  versionFileText?: string;
}): string;
