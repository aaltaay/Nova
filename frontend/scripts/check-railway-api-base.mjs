/**
 * Fail Railway builds if VITE_API_BASE_URL is missing. Without it, Vite bakes
 * in the dev fallback (localhost:8000) and production UIs cannot reach the API.
 */
const onRailway = Boolean(process.env.RAILWAY_PROJECT_ID);
const base = (process.env.VITE_API_BASE_URL ?? '').trim();

if (onRailway && !base) {
  console.error(
    '\n[Railway] VITE_API_BASE_URL is required for frontend builds.\n' +
      'Set it in Railway → Frontend service → Variables to your backend HTTPS URL\n' +
      '(e.g. https://your-backend.up.railway.app) with no trailing slash, then redeploy.\n',
  );
  process.exit(1);
}
