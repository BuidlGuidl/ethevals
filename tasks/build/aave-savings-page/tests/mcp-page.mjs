import fs from 'node:fs/promises';

// Page reads go to the verifier's fork, and wallet requests go to the session.
export default async ({ page }) => {
  const { origin, control } = JSON.parse(await fs.readFile('/logs/verifier/session.json', 'utf8'));
  const context = page.context();
  await context.route('**/*', async route => {
    const request = route.request();
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*',
      'access-control-allow-methods': 'POST, OPTIONS', 'access-control-allow-private-network': 'true' };
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (request.url() === control + '/wallet') return route.continue();
    let body;
    try { body = request.postDataJSON(); } catch { /* Static request. */ }
    if (body && (Array.isArray(body) ? body.every(item => typeof item.method === 'string') : typeof body.method === 'string')) {
      const response = await fetch(control + '/rpc', { method: 'POST', body: JSON.stringify(body) });
      return route.fulfill({ status: 200, headers, contentType: 'application/json', body: await response.text() });
    }
    return request.url().startsWith(origin + '/') ? route.continue() : route.abort();
  });
  await context.routeWebSocket('**/*', socket => socket.close());
  await page.addInitScript({ path: '/logs/verifier/wallet-init.js' });
};
