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
    out.push(byKey.get(key) || { id: key, ...entry });
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

  // Always resolve pinned items so their keys can suppress duplicates in
  // Recent/Frequent, even when the Pinned section itself is hidden.
  const pinnedSection = cfg.pinned && !Array.isArray(cfg.pinned) ? cfg.pinned : null;
  const pinnedSectionCfg = pinnedSection || { typeFilter: 'all', limit: 8 };
  const allPinnedItems = resolvePinned(config.pinned, byKey, pinnedSectionCfg);
  const pinnedKeys = new Set(allPinnedItems.map((i) => i.id));

  if (pinnedSection && pinnedSection.enabled) {
    pushSection(out, 'Pinned', allPinnedItems);
  }

  const headroom = config.pinned.length;

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
