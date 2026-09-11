#!/usr/bin/env node
// Local preview for the marketing site (site/), including its Vercel functions.
//
//   node scripts/serve-site.mjs [port]
//   open http://127.0.0.1:4321
//
// Vercel is the only place site/api/*.mjs normally runs, so without this there
// is no way to exercise /api/ai-trading-news before deploying. Serves static
// files from site/ and dispatches /api/<name> to site/api/<name>.mjs with the
// small slice of the Node request/response API those handlers use.
//
// Preview only -- not a deployment target. Production is Vercel (AGENTS.md §8).

import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SITE_ROOT = fileURLToPath(new URL("../site/", import.meta.url));
const PORT = Number(process.argv[2] ?? 4321);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".xml": "application/xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

/** Give handlers the `res.status().json()` shape Vercel provides. */
function decorate(response) {
  response.status = (code) => {
    response.statusCode = code;
    return response;
  };
  response.json = (body) => {
    response.setHeader("content-type", "application/json; charset=utf-8");
    response.end(JSON.stringify(body));
    return response;
  };
  return response;
}

async function serveFunction(name, request, response) {
  const modulePath = join(SITE_ROOT, "api", `${name}.mjs`);
  try {
    await stat(modulePath);
  } catch {
    return false;
  }
  // No cache-busting: busting only the handler URL would still reuse cached
  // _lib modules and serve stale results that look fresh. Restart after edits.
  const module = await import(pathToFileURL(modulePath).href);
  await module.default(request, decorate(response));
  return true;
}

async function resolveStatic(pathname) {
  const relative = normalize(decodeURIComponent(pathname)).replace(/^(\.\.[/\\])+/, "");
  const candidates = [relative, `${relative}.html`, join(relative, "index.html")];
  for (const candidate of candidates) {
    const filePath = join(SITE_ROOT, candidate);
    if (!filePath.startsWith(SITE_ROOT)) continue;
    try {
      if ((await stat(filePath)).isFile()) return filePath;
    } catch {
      // Try the next candidate; a miss on one shape is expected.
    }
  }
  return null;
}

const server = createServer(async (request, response) => {
  const { pathname } = new URL(request.url, `http://${request.headers.host}`);
  try {
    const apiMatch = pathname.match(/^\/api\/([\w-]+)\/?$/);
    if (apiMatch && (await serveFunction(apiMatch[1], request, response))) return;

    const filePath = await resolveStatic(pathname === "/" ? "index.html" : pathname);
    if (!filePath) {
      response.writeHead(404, { "content-type": "text/plain" }).end("Not found");
      return;
    }
    response.writeHead(200, { "content-type": MIME[extname(filePath)] ?? "application/octet-stream" });
    response.end(await readFile(filePath));
  } catch (error) {
    console.error(`[serve-site] ${pathname}:`, error);
    if (!response.headersSent) response.writeHead(500, { "content-type": "text/plain" });
    response.end("Server error");
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[serve-site] http://127.0.0.1:${PORT} -> ${SITE_ROOT}`);
});
