import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';

// Serve files without loading package scripts, Vite configuration, or links outside dist.
export async function serveBuild(workspace, port) {
  const directory = path.join(workspace, 'dist');
  if ((await fs.lstat(directory)).isSymbolicLink()) throw new Error('The built dist directory is a symbolic link');
  const root = await fs.realpath(directory);
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
    '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };
  const server = http.createServer(async (request, response) => {
    try {
      const name = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
      let target = path.resolve(root, `.${name}`);
      if (!target.startsWith(root + path.sep) && target !== root) throw new Error('Path is outside dist');
      try { if (!(await fs.stat(target)).isFile()) target = path.join(root, 'index.html'); }
      catch { target = path.join(root, 'index.html'); }
      target = await fs.realpath(target);
      if (!target.startsWith(root + path.sep)) throw new Error('File is outside dist');
      response.writeHead(200, { 'content-type': types[path.extname(target)] || 'application/octet-stream' });
      response.end(await fs.readFile(target));
    } catch {
      response.writeHead(404);
      response.end('Build file was not found.');
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
  return server;
}
