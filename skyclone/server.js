import http from 'node:http';
import './src/env.js';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { runFlightSearch } from './src/searchEngine.js';
import { getProviderNames } from './src/providers/index.js';

const root = fileURLToPath(new URL('.', import.meta.url));
const publicDir = join(root, 'public');
const searches = new Map();

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8'
};

function sendJson(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(body));
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function validateQuery(body) {
  const origin = String(body.origin || '').trim().toUpperCase();
  const destination = String(body.destination || '').trim().toUpperCase();
  const date = String(body.date || '').trim();
  const returnDate = String(body.returnDate || '').trim();
  const passengers = Number(body.passengers || 1);

  if (!/^[A-Z]{3}$/.test(origin)) throw new Error('Origin must be a 3-letter IATA code.');
  if (!/^[A-Z]{3}$/.test(destination)) throw new Error('Destination must be a 3-letter IATA code.');
  if (origin === destination) throw new Error('Origin and destination must be different.');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('Date must use YYYY-MM-DD.');
  if (returnDate && !/^\d{4}-\d{2}-\d{2}$/.test(returnDate)) throw new Error('Return date must use YYYY-MM-DD.');
  if (!Number.isInteger(passengers) || passengers < 1 || passengers > 9) {
    throw new Error('Passengers must be between 1 and 9.');
  }

  return { origin, destination, date, returnDate: returnDate || null, passengers };
}

async function serveStatic(req, res) {
  const url = new URL(req.url, 'http://localhost');
  const pathname = url.pathname === '/' ? '/index.html' : url.pathname;
  const safePath = normalize(pathname).replace(/^(\.\.[/\\])+/, '');
  const filePath = join(publicDir, safePath);
  if (!filePath.startsWith(publicDir)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  try {
    const content = await readFile(filePath);
    res.writeHead(200, { 'content-type': mimeTypes[extname(filePath)] || 'application/octet-stream' });
    res.end(content);
  } catch {
    res.writeHead(404);
    res.end('Not found');
  }
}

async function handleApi(req, res) {
  const url = new URL(req.url, 'http://localhost');

  if (req.method === 'GET' && url.pathname === '/api/providers') {
    sendJson(res, 200, { providers: getProviderNames() });
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/search') {
    try {
      const query = validateQuery(await readBody(req));
      const searchId = randomUUID();
      const startedAt = new Date().toISOString();
      const result = await runFlightSearch(query);
      const payload = { searchId, startedAt, finishedAt: new Date().toISOString(), query, ...result };
      searches.set(searchId, payload);
      sendJson(res, 200, payload);
    } catch (error) {
      sendJson(res, 400, { error: error.message });
    }
    return;
  }

  const searchMatch = /^\/api\/search\/([^/]+)$/.exec(url.pathname);
  if (req.method === 'GET' && searchMatch) {
    const result = searches.get(searchMatch[1]);
    sendJson(res, result ? 200 : 404, result || { error: 'Search not found.' });
    return;
  }

  const providerMatch = /^\/api\/search\/([^/]+)\/flights\/([^/]+)\/providers$/.exec(url.pathname);
  if (req.method === 'GET' && providerMatch) {
    const result = searches.get(providerMatch[1]);
    const flightKey = decodeURIComponent(providerMatch[2]);
    const flight = result?.flights.find(item => item.flightKey === flightKey);
    sendJson(res, flight ? 200 : 404, flight ? { providers: flight.providers } : { error: 'Flight not found.' });
    return;
  }

  sendJson(res, 404, { error: 'API route not found.' });
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      await handleApi(req, res);
      return;
    }
    await serveStatic(req, res);
  } catch (error) {
    sendJson(res, 500, { error: error.message });
  }
});

const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || '127.0.0.1';
server.listen(port, host, () => {
  console.log(`Skyclone running at http://${host}:${port}`);
});
