'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { mergeConfig } = require('./core/config.js');

function loadConfig(filePath, log) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return { config: mergeConfig(JSON.parse(raw)), existed: true };
  } catch (err) {
    if (err.code !== 'ENOENT' && log) log.error(`config load failed, using defaults: ${err.message}`);
    return { config: mergeConfig({}), existed: false };
  }
}

function saveConfig(filePath, config) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(mergeConfig(config), null, 2));
}

module.exports = { loadConfig, saveConfig };
