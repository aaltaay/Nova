export function readVersionFileText(versionFile: string): string;
export function releaseTagFromGit(cwd: string): string;
export function resolveReleaseTag(opts?: { versionFile?: string; cwd?: string }): string;
