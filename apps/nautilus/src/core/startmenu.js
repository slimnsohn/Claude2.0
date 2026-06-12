'use strict';

const path = require('node:path');

// Start Menus are shallow; the cap only exists so a junction/symlink loop
// can't recurse forever.
const MAX_DEPTH = 8;

function scanDir(root, dir, depth, listDirSync, out) {
  if (depth > MAX_DEPTH) return;
  let entries;
  try {
    entries = listDirSync(dir);
  } catch {
    return; // missing/unreadable dir — skip
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory) {
      scanDir(root, full, depth + 1, listDirSync, out);
    } else if (/\.lnk$/i.test(entry.name)) {
      out.push({
        id: `app:${full}`,
        type: 'app',
        title: entry.name.replace(/\.lnk$/i, ''),
        subtitle: path.relative(root, dir),
        target: full,
      });
    }
  }
}

function scanStartMenu(roots, { listDirSync }) {
  const out = [];
  for (const root of roots) {
    scanDir(root, root, 0, listDirSync, out);
  }
  // User + system Start Menus often hold the same shortcut; first root wins.
  const seen = new Set();
  return out.filter((item) => {
    const key = item.title.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

module.exports = { scanStartMenu };
