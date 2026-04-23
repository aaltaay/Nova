/**
 * Fail Railway builds if VITE_API_BASE_URL is missing. Without it, Vite bakes
 * in the dev fallback (localhost:8000) and production UIs cannot reach the API.
 */
const onRailway = Boolean(process.env.RAILWAY_PROJECT_ID);
const base = (
  process.env.VITE_API_BASE_URL ??
  process.env.NOVA_API_BASE ??
  ''
).trim();

if (onRailway && !base) {
  console.error(
    '\n[Railway] Set VITE_API_BASE_URL (or NOVA_API_BASE) for frontend builds.\n' +
      'Railway → Frontend → Variables, e.g. https://your-backend.up.railway.app\n' +
      'Or reference the backend: https://${{Backend.RAILWAY_PUBLIC_DOMAIN}} (no trailing slash).\n',
  );
  process.exit(1);
}
