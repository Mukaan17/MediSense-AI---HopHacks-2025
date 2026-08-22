/* Minimal static server for the CRA build with SPA fallback.
   No dependencies, so the E2E stack needs nothing beyond node itself. */
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = Number(process.env.E2E_WEB_PORT || 3080);
const ROOT = path.resolve(__dirname, '..', 'build');

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.map': 'application/json', '.txt': 'text/plain',
  '.woff': 'font/woff', '.woff2': 'font/woff2',
};

http.createServer((req, res) => {
  const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
  let filePath = path.normalize(path.join(ROOT, urlPath));
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403).end();
    return;
  }
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(ROOT, 'index.html'); // SPA fallback
  }
  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
  fs.createReadStream(filePath).pipe(res);
}).listen(PORT, () => console.log(`e2e static server on :${PORT} serving ${ROOT}`));
