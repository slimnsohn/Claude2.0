/**
 * FetchWrapper — Reusable fetch wrapper for browser-based apps.
 * Automatic retry, rate limiting, timeout, consistent error formatting.
 * Zero dependencies. Works via <script> tag or ES module import.
 */
(function (root, factory) {
  if (typeof exports === 'object' && typeof module === 'object') {
    module.exports = factory();
  } else if (typeof define === 'function' && define.amd) {
    define(factory);
  } else {
    root.FetchWrapper = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DEFAULT_TIMEOUT = 10000;
  const DEFAULT_RETRIES = 3;
  const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);

  /**
   * Simple token-bucket rate limiter.
   * Allows `rps` requests per second, queuing excess calls.
   */
  class RateLimiter {
    constructor(rps) {
      this.interval = 1000 / rps;
      this.lastCall = 0;
      this.queue = [];
      this.processing = false;
    }

    async acquire() {
      return new Promise((resolve) => {
        this.queue.push(resolve);
        if (!this.processing) this._process();
      });
    }

    _process() {
      if (this.queue.length === 0) {
        this.processing = false;
        return;
      }
      this.processing = true;
      const now = Date.now();
      const wait = Math.max(0, this.interval - (now - this.lastCall));
      setTimeout(() => {
        this.lastCall = Date.now();
        const next = this.queue.shift();
        if (next) next();
        this._process();
      }, wait);
    }
  }

  /**
   * Build a consistent response envelope.
   */
  function makeResult(ok, data, error, status) {
    return { ok, data, error, status };
  }

  /**
   * Parse response body as JSON, falling back to text.
   */
  async function parseBody(response) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json();
    }
    return response.text();
  }

  /**
   * Create a fetch wrapper instance.
   */
  function create(options = {}) {
    const baseUrl = (options.baseUrl || '').replace(/\/+$/, '');
    const defaultHeaders = options.headers || {};
    const maxRetries = options.retries ?? DEFAULT_RETRIES;
    const timeout = options.timeout ?? DEFAULT_TIMEOUT;
    const limiter = options.rateLimit ? new RateLimiter(options.rateLimit) : null;

    /**
     * Core request method. All HTTP verb helpers delegate here.
     */
    async function request(method, path, body, requestOptions = {}) {
      const url = baseUrl ? baseUrl + path : path;
      const headers = { ...defaultHeaders, ...requestOptions.headers };
      const retries = requestOptions.retries ?? maxRetries;
      const reqTimeout = requestOptions.timeout ?? timeout;

      if (body != null && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof Blob)) {
        if (!headers['Content-Type'] && !headers['content-type']) {
          headers['Content-Type'] = 'application/json';
        }
        body = JSON.stringify(body);
      }

      let lastError = null;
      let lastStatus = 0;

      for (let attempt = 0; attempt <= retries; attempt++) {
        // Wait for rate limiter slot
        if (limiter) await limiter.acquire();

        // Exponential backoff on retries
        if (attempt > 0) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
          await new Promise((r) => setTimeout(r, delay));
        }

        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), reqTimeout);

        try {
          const fetchOpts = {
            method,
            headers,
            signal: controller.signal,
          };
          if (body != null && method !== 'GET' && method !== 'HEAD') {
            fetchOpts.body = body;
          }

          const response = await fetch(url, fetchOpts);
          clearTimeout(timer);

          lastStatus = response.status;

          if (response.ok) {
            const data = await parseBody(response);
            return makeResult(true, data, null, response.status);
          }

          // Non-OK response — decide whether to retry
          const responseBody = await parseBody(response);
          lastError = typeof responseBody === 'string' ? responseBody : JSON.stringify(responseBody);

          if (!RETRYABLE_STATUS_CODES.has(response.status) || attempt === retries) {
            return makeResult(false, null, lastError, response.status);
          }
          // Otherwise loop and retry
        } catch (err) {
          clearTimeout(timer);
          lastStatus = 0;

          if (err.name === 'AbortError') {
            lastError = `Request timed out after ${reqTimeout}ms`;
          } else {
            lastError = err.message || String(err);
          }

          if (attempt === retries) {
            return makeResult(false, null, lastError, lastStatus);
          }
        }
      }

      // Should not reach here, but safety net
      return makeResult(false, null, lastError, lastStatus);
    }

    return {
      request,
      get(path, options) {
        return request('GET', path, null, options);
      },
      post(path, body, options) {
        return request('POST', path, body, options);
      },
      put(path, body, options) {
        return request('PUT', path, body, options);
      },
      delete(path, options) {
        return request('DELETE', path, null, options);
      },
    };
  }

  return { create };
});
