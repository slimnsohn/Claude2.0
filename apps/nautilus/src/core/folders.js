'use strict';

const path = require('node:path');

const SKIP = new Set(['node_modules', '$recycle.bin', 'system volume information']);

function shouldSkip(name) {
  return name.startsWith('.') || SKIP.has(name.toLowerCase());
}

function scanDir(dir, depth, maxDepth, listDirSync, out) {
  if (depth > maxDepth) return;
  let entries;
  try {
    entries = listDirSync(dir);
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory || shouldSkip(entry.name)) continue;
    const full = path.join(dir, entry.name);
    out.push({
      id: `dir:${full}`,
      type: 'folder',
      title: entry.name,
      subtitle: dir,
      target: full,
    });
    scanDir(full, depth + 1, maxDepth, listDirSync, out);
  }
}

function scanFolders(roots, { listDirSync, maxDepth = 2 }) {
  const out = [];
  for (const root of roots) {
    try {
      listDirSync(root); // existence check — missing roots are skipped entirely
    } catch {
      continue;
    }
    out.push({
      id: `dir:${root}`,
      type: 'folder',
      title: path.basename(root),
      subtitle: path.dirname(root),
      target: root,
    });
    scanDir(root, 1, maxDepth, listDirSync, out);
  }
  return out;
}

module.exports = { scanFolders };
