'use strict';

function normalizeUrl(url) {
  return String(url || '').toLowerCase().replace(/\/+$/, '');
}

function hostOf(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

function walk(node, out) {
  for (const child of node.children || []) {
    if (child.type === 'url' && child.url) {
      out.push({
        id: `bm:${child.url}`,
        type: 'site',
        title: child.name || child.url,
        subtitle: hostOf(child.url),
        target: child.url,
      });
    } else if (child.type === 'folder') {
      walk(child, out);
    }
  }
}

// Parses Chrome's Bookmarks file content; only the bookmarks bar is indexed.
// Throws on bad JSON or unexpected shape — callers keep the last good index.
function parseBookmarks(jsonText) {
  const data = JSON.parse(jsonText);
  const bar = data && data.roots && data.roots.bookmark_bar;
  if (!bar || typeof bar !== 'object') {
    throw new Error('Bookmarks file missing roots.bookmark_bar');
  }
  const out = [];
  walk(bar, out);
  return out;
}

function mergeSites(bookmarkItems, builtins) {
  const seen = new Set(bookmarkItems.map((i) => normalizeUrl(i.target)));
  const extra = builtins.filter((b) => !seen.has(normalizeUrl(b.target)));
  return [...bookmarkItems, ...extra];
}

module.exports = { parseBookmarks, mergeSites };
