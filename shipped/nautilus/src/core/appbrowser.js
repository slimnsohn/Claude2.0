'use strict';

// Pure helpers for the Settings "All Applications" browser. Dual-mode: required
// by node:test AND loaded as a plain <script> in config.html (window.appbrowser),
// since the renderer has no nodeIntegration.
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.appbrowser = api;
}(typeof self !== 'undefined' ? self : this, function () {
  function pinKey(item) {
    return `${item.type}:${item.target}`;
  }

  function isPinned(pinned, item) {
    const k = pinKey(item);
    return (pinned || []).some((e) => pinKey(e) === k);
  }

  function filterItems(items, { type = 'all', query = '' } = {}) {
    const q = query.trim().toLowerCase();
    return (items || [])
      .filter((it) => type === 'all' || it.type === type)
      .filter((it) => !q || String(it.title || '').toLowerCase().includes(q))
      .slice()
      .sort((a, b) => String(a.title || '').localeCompare(String(b.title || ''), undefined, { sensitivity: 'base' }));
  }

  // Return a copy of arr with the element at `from` moved to index `to`.
  // Out-of-range or no-op moves return an unchanged copy.
  function move(arr, from, to) {
    const out = (arr || []).slice();
    if (from < 0 || from >= out.length) return out;
    if (to < 0 || to >= out.length || to === from) return out;
    const [item] = out.splice(from, 1);
    out.splice(to, 0, item);
    return out;
  }

  return { pinKey, isPinned, filterItems, move };
}));
