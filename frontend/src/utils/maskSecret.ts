/** Mask a secret for display — show only trailing chars. */
export function maskSecret(value: string | null | undefined, visible = 4): string {
  if (!value) return '';
  if (value.length <= visible) return '*'.repeat(value.length);
  return '*'.repeat(value.length - visible) + value.slice(-visible);
}
