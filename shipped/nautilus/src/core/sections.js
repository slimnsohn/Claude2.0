'use strict';

const { recent, frequent } = require('./history.js');

function indexByKey(index) {
  const map = new Map();
  for (const it of index || []) map.set(`${it.type}:${it.target}`, it);
  return map;
}

function resolvePinned(pinned, byKey, { typeFilter, limit }) {
  const out = [];
  for (const entry of pinned) {
    if (typeFilter !== 'all' && entry.type !== typeFilter) continue;
    const key = `${entry.type}:${entry.target}`;
    const live = byKey.get(key);
    out.push(live ? { ...live, id: key } : { id: key, ...entry });
    if (out.length >= limit) break;
  }
  return out;
}

function pushSection(out, label, items) {
  if (!items.length) return;
  out.push({ kind: 'header', label });
  for (const item of items) out.push({ kind: 'item', item });
}

function buildHome({ config, history, index }) {
  const byKey = indexByKey(index);
  const cfg = config.sections;
  const out = [];
  const pinnedKeys = new Set();
  let headroom = 0;

  if (cfg.pinned.enabled) {
    const items = resolvePinned(config.pinned, byKey, cfg.pinned);
    items.forEach((i) => pinnedKeys.add(i.id));
    pushSection(out, 'Pinned', items);
    headroom = items.length;
  }

  if (cfg.recent.enabled) {
    const items = recent(history, { typeFilter: cfg.recent.typeFilter, limit: cfg.recent.limit + headroom })
      .filter((i) => !pinnedKeys.has(i.id))
      .slice(0, cfg.recent.limit);
    pushSection(out, 'Recent', items);
  }

  if (cfg.frequent.enabled) {
    const items = frequent(history, { typeFilter: cfg.frequent.typeFilter, limit: cfg.frequent.limit + headroom })
      .filter((i) => !pinnedKeys.has(i.id))
      .slice(0, cfg.frequent.limit);
    pushSection(out, 'Frequent', items);
  }

  return out;
}

module.exports = { buildHome };
