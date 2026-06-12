'use strict';

// Built-in jump targets, merged with the Chrome bookmarks bar (bookmarks win
// on URL collisions — see bookmarks.mergeSites).
function site(title, target, subtitle) {
  return { id: `builtin:${title.toLowerCase()}`, type: 'site', title, subtitle: subtitle || new URL(target).hostname, target };
}

const BUILTIN_SITES = [
  site('Gmail', 'https://mail.google.com'),
  site('Claude', 'https://claude.ai'),
  site('ESPN', 'https://www.espn.com'),
  site('YouTube', 'https://www.youtube.com'),
  site('Google Calendar', 'https://calendar.google.com'),
  site('Google Drive', 'https://drive.google.com'),
  site('Google Maps', 'https://maps.google.com'),
  site('GitHub', 'https://github.com'),
  site('Amazon', 'https://www.amazon.com'),
  site('Netflix', 'https://www.netflix.com'),
];

module.exports = { BUILTIN_SITES };
