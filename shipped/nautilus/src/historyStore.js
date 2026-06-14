'use strict';

const fs = require('node:fs');
const path = require('node:path');

const EMPTY = () => ({ version: 1, items: {} });

function loadHistory(filePath, log) {
  try {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    if (data && typeof data.items === 'object' && data.items !== null && !Array.isArray(data.items)) {
      return { version: 1, items: data.items };
    }
    return EMPTY();
  } catch (err) {
    if (err.code !== 'ENOENT' && log) log.error(`history load failed, starting empty: ${err.message}`);
    return EMPTY();
  }
}

function saveHistory(filePath, history) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(history, null, 2));
}

module.exports = { loadHistory, saveHistory };
