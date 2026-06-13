'use strict';

const fs = require('node:fs');
const path = require('node:path');

// Best-effort append-only logger. Logging must never take the launcher down.
function createLogger(logPath) {
  function write(level, message) {
    try {
      fs.mkdirSync(path.dirname(logPath), { recursive: true });
      fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${level} ${message}\n`);
    } catch {
      // swallow — nowhere safe to report a logger failure
    }
  }
  return {
    info: (message) => write('INFO', message),
    error: (message) => write('ERROR', message),
  };
}

module.exports = { createLogger };
