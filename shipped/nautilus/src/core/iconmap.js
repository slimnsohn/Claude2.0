'use strict';

const path = require('node:path');

// Bundled flat icons live here. attachIcons (main.js) reads these and inlines
// them as data: URLs; the renderer just shows item.icon if present.
const ICON_DIR = path.join(__dirname, '..', '..', 'assets', 'app-icons');

// One token (word) in the app title → icon slug. Token-equality, not substring,
// so "Crossword" never maps to Word. First match wins. Slug == "<slug>.svg".
const TOKEN_SLUGS = [
  ['cursor', 'cursor'],
  ['excel', 'excel'],
  ['word', 'word'],
  ['powerpoint', 'powerpoint'],
  ['outlook', 'outlook'],
  ['onenote', 'onenote'],
  ['publisher', 'publisher'],
  ['access', 'access'],
  ['chrome', 'chrome'],
  ['edge', 'edge'],
  ['discord', 'discord'],
  ['vlc', 'vlc'],
  ['claude', 'claude'],
  ['dropbox', 'dropbox'],
  ['teamviewer', 'teamviewer'],
  ['pycharm', 'pycharm'],
  ['anaconda', 'anaconda'],
  ['jupyter', 'jupyter'],
  ['node', 'node'],
  ['git', 'git'],
];

function tokenize(title) {
  return String(title || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

// App title → icon slug, or null if we don't bundle one.
function iconSlug(title) {
  if (!title) return null;
  const tokens = tokenize(title);
  for (const [token, slug] of TOKEN_SLUGS) {
    if (tokens.includes(token)) return slug;
  }
  return null;
}

// Resolve an index item to a bundled icon filename, or null (→ badge/favicon).
function iconFor(item) {
  if (!item) return null;
  if (item.type === 'folder') return 'folder.svg';
  if (item.type === 'app') {
    const slug = iconSlug(item.title);
    return slug ? `${slug}.svg` : null;
  }
  return null;
}

module.exports = { iconSlug, iconFor, ICON_DIR };
