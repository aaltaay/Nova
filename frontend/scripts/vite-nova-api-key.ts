/** Local Vite serve only -- map repo NOVA_API_KEY onto VITE_NOVA_API_KEY. */
export function readDevNovaApiKey(env: Record<string, string | undefined>): string {
  const fromVite = (env.VITE_NOVA_API_KEY || '').trim();
  if (fromVite) return fromVite;
  return (env.NOVA_API_KEY || '').trim();
}
