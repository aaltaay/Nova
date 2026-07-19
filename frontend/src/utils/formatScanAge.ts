/** Humanize scanner / price age for the header status cluster. */

export function formatScanAge(secondsAgo: number): string {
  const s = Math.max(0, Math.floor(secondsAgo));
  if (s < 60) return `${s}s ago`;
  const mins = Math.floor(s / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
