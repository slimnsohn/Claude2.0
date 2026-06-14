'use strict';

const TYPE_FILTERS = new Set(['all', 'app', 'folder', 'site']);
const PINNABLE = new Set(['app', 'folder', 'site']);
const SEED_NAMES = ['Cursor', 'Notepad', 'Excel'];

const DEFAULT_CONFIG = {
  version: 1,
  sections: {
    pinned: { enabled: true, typeFilter: 'all', limit: 8 },
    recent: { enabled: true, typeFilter: 'all', limit: 5 },
    frequent: { enabled: true, typeFilter: 'all', limit: 5 },
  },
  pinned: [],
};

function mergeSection(part, def) {
  const p = part && typeof part === 'object' ? part : {};
  const limit = Number.isInteger(p.limit) && p.limit >= 0 ? p.limit : def.limit;
  return {
    enabled: typeof p.enabled === 'boolean' ? p.enabled : def.enabled,
    typeFilter: TYPE_FILTERS.has(p.typeFilter) ? p.typeFilter : def.typeFilter,
    limit,
  };
}

function cleanPinned(list) {
  if (!Array.isArray(list)) return [];
  return list
    .filter((e) => e && PINNABLE.has(e.type) && typeof e.target === 'string' && e.target)
    .map((e) => ({
      type: e.type,
      title: typeof e.title === 'string' && e.title ? e.title : e.target,
      subtitle: typeof e.subtitle === 'string' ? e.subtitle : '',
      target: e.target,
    }));
}

function mergeConfig(partial) {
  const p = partial && typeof partial === 'object' ? partial : {};
  const sec = p.sections && typeof p.sections === 'object' ? p.sections : {};
  return {
    version: 1,
    sections: {
      pinned: mergeSection(sec.pinned, DEFAULT_CONFIG.sections.pinned),
      recent: mergeSection(sec.recent, DEFAULT_CONFIG.sections.recent),
      frequent: mergeSection(sec.frequent, DEFAULT_CONFIG.sections.frequent),
    },
    pinned: cleanPinned(p.pinned),
  };
}

// Best-effort first-run pins: exact app-title match first, then substring.
function seedPinned(index, names = SEED_NAMES) {
  const apps = (index || []).filter((i) => i.type === 'app');
  const out = [];
  for (const name of names) {
    const lc = name.toLowerCase();
    const match = apps.find((i) => (i.title || '').toLowerCase() === lc)
      || apps.find((i) => (i.title || '').toLowerCase().includes(lc));
    if (match) out.push({ type: 'app', title: match.title, subtitle: match.subtitle || '', target: match.target });
  }
  return out;
}

module.exports = { DEFAULT_CONFIG, TYPE_FILTERS, PINNABLE, SEED_NAMES, mergeConfig, seedPinned };
