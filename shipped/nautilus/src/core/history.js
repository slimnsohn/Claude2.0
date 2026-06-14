'use strict';

const TRACKABLE = new Set(['app', 'folder', 'site']);

function keyOf(item) {
  return `${item.type}:${item.target}`;
}

function record(history, item, now) {
  if (!item || !TRACKABLE.has(item.type) || !item.target) return history;
  // Shallow copy is safe: record() is the only writer and always assigns a fresh
  // entry object for the touched key, so existing entries are never mutated in place.
  const items = { ...(history && history.items) };
  const key = keyOf(item);
  const prev = items[key] || { count: 0 };
  items[key] = {
    type: item.type,
    title: item.title || item.target,
    subtitle: item.subtitle || '',
    target: item.target,
    count: prev.count + 1,
    lastLaunched: now,
  };
  return { version: 1, items }; // version: schema version for future migrations
}

function toItem(rec) {
  return { id: keyOf(rec), type: rec.type, title: rec.title, subtitle: rec.subtitle, target: rec.target };
}

function select(history, sortFn, { typeFilter = 'all', limit = 5 } = {}) {
  const list = Object.values((history && history.items) || {}).sort(sortFn);
  const filtered = typeFilter === 'all' ? list : list.filter((i) => i.type === typeFilter);
  return filtered.slice(0, limit).map(toItem);
}

function recent(history, opts) {
  return select(history, (a, b) => b.lastLaunched - a.lastLaunched, opts);
}

function frequent(history, opts) {
  return select(history, (a, b) => b.count - a.count || b.lastLaunched - a.lastLaunched, opts);
}

module.exports = { record, recent, frequent, keyOf };
