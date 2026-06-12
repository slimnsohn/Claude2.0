'use strict';

const path = require('node:path');

function scanDir(root, dir, listDirSync, out) {
  let entries;
  try {
    entries = listDirSync(dir);
  } catch {
    return; // missing/unreadable dir — skip
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory) {
      scanDir(root, full, listDirSync, out);
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
    scanDir(root, root, listDirSync, out);
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
