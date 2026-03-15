/**
 * fetch-wrapper.test.js — Browser-based tests for FetchWrapper.
 *
 * Usage:
 *   Open in a browser via a simple HTML page that includes fetch-wrapper.js
 *   before this file, or run with Node (needs a global fetch polyfill for Node < 18).
 *
 *   <script src="fetch-wrapper.js"></script>
 *   <script src="fetch-wrapper.test.js"></script>
 */
(async function () {
  'use strict';

  // ─── Mini test runner ───────────────────────────────────────────────
  let passed = 0;
  let failed = 0;
  const failures = [];

  function assert(condition, message) {
    if (!condition) throw new Error('Assertion failed: ' + message);
  }

  function assertEqual(actual, expected, label) {
    if (actual !== expected) {
      throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
  }

  async function test(name, fn) {
    try {
      await fn();
      passed++;
      console.log(`  PASS  ${name}`);
    } catch (err) {
      failed++;
      failures.push({ name, error: err.message });
      console.error(`  FAIL  ${name}\n        ${err.message}`);
    }
  }

  // ─── Fake fetch ─────────────────────────────────────────────────────
  // We monkey-patch globalThis.fetch for isolated, dependency-free testing.
  const _originalFetch = globalThis.fetch;
  let fetchMock = null;

  function mockFetch(handler) {
    fetchMock = handler;
    globalThis.fetch = async function (url, opts) {
      return fetchMock(url, opts);
    };
  }

  function restoreFetch() {
    globalThis.fetch = _originalFetch;
    fetchMock = null;
  }

  // Helper: create a fake Response
  function fakeResponse(status, body, contentType = 'application/json') {
    const isJson = contentType.includes('json');
    const bodyStr = isJson ? JSON.stringify(body) : String(body);
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: {
        get(key) {
          if (key.toLowerCase() === 'content-type') return contentType;
          return null;
        },
      },
      json: async () => (isJson ? body : JSON.parse(bodyStr)),
      text: async () => bodyStr,
    };
  }

  // Resolve FetchWrapper from global or module scope
  const FW = typeof FetchWrapper !== 'undefined' ? FetchWrapper : require('./fetch-wrapper.js');

  // ─── Tests ──────────────────────────────────────────────────────────
  console.log('\nfetch-wrapper tests\n');

  // -- Successful GET --------------------------------------------------
  await test('GET success returns { ok: true, data, status }', async () => {
    mockFetch(async () => fakeResponse(200, { id: 1, name: 'Alice' }));
    const api = FW.create({ baseUrl: 'https://api.test', retries: 0 });
    const res = await api.get('/users/1');
    assertEqual(res.ok, true, 'ok');
    assertEqual(res.status, 200, 'status');
    assertEqual(res.data.name, 'Alice', 'data.name');
    assertEqual(res.error, null, 'error');
    restoreFetch();
  });

  // -- Successful POST ------------------------------------------------
  await test('POST sends JSON body and returns data', async () => {
    let capturedBody = null;
    let capturedHeaders = {};
    mockFetch(async (url, opts) => {
      capturedBody = opts.body;
      capturedHeaders = opts.headers;
      return fakeResponse(201, { id: 42 });
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 0 });
    const res = await api.post('/items', { title: 'New' });
    assertEqual(res.ok, true, 'ok');
    assertEqual(res.status, 201, 'status');
    assertEqual(res.data.id, 42, 'data.id');
    assertEqual(capturedHeaders['Content-Type'], 'application/json', 'content-type header');
    assertEqual(capturedBody, '{"title":"New"}', 'serialized body');
    restoreFetch();
  });

  // -- Retry on 500 ---------------------------------------------------
  await test('Retries on 500 and succeeds on second attempt', async () => {
    let calls = 0;
    mockFetch(async () => {
      calls++;
      if (calls === 1) return fakeResponse(500, { error: 'Internal' });
      return fakeResponse(200, { recovered: true });
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 2, rateLimit: 100 });
    const res = await api.get('/flaky');
    assertEqual(res.ok, true, 'ok after retry');
    assertEqual(calls, 2, 'called twice');
    restoreFetch();
  });

  // -- Exhausted retries on 500 ----------------------------------------
  await test('Returns error after exhausting retries on 500', async () => {
    let calls = 0;
    mockFetch(async () => {
      calls++;
      return fakeResponse(500, { error: 'still broken' });
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 1, rateLimit: 100 });
    const res = await api.get('/broken');
    assertEqual(res.ok, false, 'ok is false');
    assertEqual(res.status, 500, 'status 500');
    assert(res.error !== null, 'error present');
    assertEqual(calls, 2, 'initial + 1 retry = 2 calls');
    restoreFetch();
  });

  // -- No retry on 404 ------------------------------------------------
  await test('Does not retry on 404 (non-retryable status)', async () => {
    let calls = 0;
    mockFetch(async () => {
      calls++;
      return fakeResponse(404, 'Not Found', 'text/plain');
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 3, rateLimit: 100 });
    const res = await api.get('/missing');
    assertEqual(res.ok, false, 'ok is false');
    assertEqual(res.status, 404, 'status');
    assertEqual(calls, 1, 'only 1 call (no retry)');
    restoreFetch();
  });

  // -- Timeout --------------------------------------------------------
  await test('Request times out and returns error', async () => {
    mockFetch(async (url, opts) => {
      // Simulate slow server by waiting for abort
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => resolve(fakeResponse(200, {})), 60000);
        if (opts.signal) {
          opts.signal.addEventListener('abort', () => {
            clearTimeout(timer);
            const err = new Error('The operation was aborted');
            err.name = 'AbortError';
            reject(err);
          });
        }
      });
    });
    const api = FW.create({ baseUrl: 'https://api.test', timeout: 50, retries: 0 });
    const res = await api.get('/slow');
    assertEqual(res.ok, false, 'ok is false');
    assert(res.error.includes('timed out'), 'error mentions timeout');
    restoreFetch();
  });

  // -- Rate limiting --------------------------------------------------
  await test('Rate limiter spaces requests correctly', async () => {
    const timestamps = [];
    mockFetch(async () => {
      timestamps.push(Date.now());
      return fakeResponse(200, { t: Date.now() });
    });
    // 10 requests per second = 100ms between requests
    const api = FW.create({ baseUrl: 'https://api.test', rateLimit: 10, retries: 0 });
    await Promise.all([api.get('/a'), api.get('/b'), api.get('/c')]);
    assertEqual(timestamps.length, 3, 'all 3 requests made');
    // Check that there is at least ~80ms gap between consecutive calls
    // (allowing some timer jitter)
    for (let i = 1; i < timestamps.length; i++) {
      const gap = timestamps[i] - timestamps[i - 1];
      assert(gap >= 70, `Gap between request ${i - 1} and ${i} was ${gap}ms, expected >= 70ms`);
    }
    restoreFetch();
  });

  // -- Error formatting -----------------------------------------------
  await test('Network error returns consistent envelope', async () => {
    mockFetch(async () => {
      throw new TypeError('Failed to fetch');
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 0 });
    const res = await api.get('/offline');
    assertEqual(res.ok, false, 'ok is false');
    assertEqual(res.data, null, 'data is null');
    assertEqual(res.status, 0, 'status is 0 for network error');
    assert(res.error.includes('Failed to fetch'), 'error message preserved');
    restoreFetch();
  });

  // -- Custom headers -------------------------------------------------
  await test('Custom headers are sent (default + per-request)', async () => {
    let capturedHeaders = {};
    mockFetch(async (url, opts) => {
      capturedHeaders = opts.headers;
      return fakeResponse(200, {});
    });
    const api = FW.create({
      baseUrl: 'https://api.test',
      retries: 0,
      headers: { Authorization: 'Bearer tok123' },
    });
    const res = await api.get('/secure', { headers: { 'X-Custom': 'yes' } });
    assertEqual(res.ok, true, 'ok');
    assertEqual(capturedHeaders['Authorization'], 'Bearer tok123', 'default header');
    assertEqual(capturedHeaders['X-Custom'], 'yes', 'per-request header');
    restoreFetch();
  });

  // -- PUT method -----------------------------------------------------
  await test('PUT sends body and returns result', async () => {
    let capturedMethod = '';
    mockFetch(async (url, opts) => {
      capturedMethod = opts.method;
      return fakeResponse(200, { updated: true });
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 0 });
    const res = await api.put('/items/1', { title: 'Updated' });
    assertEqual(res.ok, true, 'ok');
    assertEqual(capturedMethod, 'PUT', 'method is PUT');
    restoreFetch();
  });

  // -- DELETE method --------------------------------------------------
  await test('DELETE sends request without body', async () => {
    let capturedMethod = '';
    let capturedBody = undefined;
    mockFetch(async (url, opts) => {
      capturedMethod = opts.method;
      capturedBody = opts.body;
      return fakeResponse(204, '', 'text/plain');
    });
    const api = FW.create({ baseUrl: 'https://api.test', retries: 0 });
    const res = await api.delete('/items/1');
    assertEqual(res.ok, true, 'ok');
    assertEqual(capturedMethod, 'DELETE', 'method is DELETE');
    assertEqual(capturedBody, undefined, 'no body on DELETE');
    restoreFetch();
  });

  // ─── Summary ────────────────────────────────────────────────────────
  console.log(`\nResults: ${passed} passed, ${failed} failed\n`);
  if (failures.length > 0) {
    console.log('Failures:');
    failures.forEach((f) => console.log(`  - ${f.name}: ${f.error}`));
  }
})();
