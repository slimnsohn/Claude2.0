'use strict';
const path = require('node:path');

// Builds a listDirSync facade from a nested object tree.
// Leaf value null = file; nested object = directory.
function makeFakeFs(tree) {
  function resolve(dir) {
    const norm = path.normalize(dir).replace(/[\\/]+$/, '');
    for (const root of Object.keys(tree)) {
      const normRoot = path.normalize(root).replace(/[\\/]+$/, '');
      if (norm.toLowerCase() === normRoot.toLowerCase()) return tree[root];
      const prefix = normRoot + path.sep;
      if (norm.toLowerCase().startsWith(prefix.toLowerCase())) {
        const rel = norm.slice(prefix.length).split(path.sep);
        let node = tree[root];
        for (const part of rel) {
          if (!node || typeof node !== 'object') return undefined;
          node = node[part];
        }
        return node;
      }
    }
    return undefined;
  }

  return function listDirSync(dir) {
    const node = resolve(dir);
    if (!node || typeof node !== 'object') {
      const err = new Error(`ENOENT: ${dir}`);
      err.code = 'ENOENT';
      throw err;
    }
    return Object.entries(node).map(([name, value]) => ({
      name,
      isDirectory: value !== null && typeof value === 'object',
    }));
  };
}

module.exports = { makeFakeFs };
