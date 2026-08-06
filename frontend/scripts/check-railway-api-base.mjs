/**
 * Legacy Railway prebuild guard (no-op unless RAILWAY_PROJECT_ID is set).
 * Nova no longer hosts on Railway -- backend is local / Desktop only.
 * Kept so old env vars do not break `npm run build` if somehow present.
 */
const onRailway =
  Boolean(process.env.RAILWAY_PROJECT_ID) && !process.env.GITHUB_ACTIONS;
const base = (
  process.env.VITE_API_BASE_URL ??
  process.env.NOVA_API_BASE ??
  ''
).trim();

if (onRailway && !base) {
  console.error(
    '\n[deprecated Railway] RAILWAY_PROJECT_ID is set but VITE_API_BASE_URL is missing.\n' +
      'Nova no longer uses Railway. Unset RAILWAY_PROJECT_ID, or set VITE_API_BASE_URL\n' +
      'for a real API host (local default is http://localhost:8000).\n',
  );
  process.exit(1);
}
