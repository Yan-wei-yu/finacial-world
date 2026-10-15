// Minimal static file server for local preview and Playwright (no dependencies).
// Usage: node scripts/serve.mjs [root=site] [port=8000]
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, resolve, sep } from 'node:path';

const ROOT = resolve(process.argv[2] ?? 'site');
const PORT = Number(process.argv[3] ?? process.env.PORT ?? 8000);
const BACKLOG = 511;
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
};

function resolveFile(rawUrl) {
  const { pathname } = new URL(rawUrl ?? '/', 'http://localhost');
  const decoded = decodeURIComponent(pathname);
  const relative = normalize(decoded.endsWith('/') ? `${decoded}index.html` : decoded);
  const file = resolve(join(ROOT, relative));
  return file === ROOT || file.startsWith(ROOT + sep) ? file : null;
}

const server = createServer(async (request, response) => {
  let file = null;
  try {
    file = resolveFile(request.url);
  } catch {
    file = null;
  }
  if (!file) {
    response.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Bad request');
    return;
  }
  try {
    const body = await readFile(file);
    response.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Cache-Control': 'no-store' });
    response.end(body);
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Not found');
  }
});

server.listen(PORT, '127.0.0.1', BACKLOG, () => {
  process.stdout.write(`Serving ${ROOT} at http://127.0.0.1:${PORT}\n`);
});
