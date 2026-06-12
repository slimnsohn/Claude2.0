'use strict';

const { rankItems } = require('./score.js');

// Substring tier or better counts as a "strong" match (see score.js tiers).
const STRONG_MATCH = 600;

const LAUNCH_VERBS = /^(open|launch|go to|start|run)\s+/i;

const QUESTION_WORDS = new Set([
  'help', 'where', 'what', 'how', 'should', 'setup', 'why', 'can',
  'who', 'when', 'is', 'does', 'do', 'will', 'would', 'which',
]);

function stripVerbs(query) {
  return String(query || '').replace(LAUNCH_VERBS, '');
}

function isQuestionShaped(query, hasStrongMatch) {
  const words = String(query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return false;
  if (QUESTION_WORDS.has(words[0])) return true;
  return words.length >= 3 && !hasStrongMatch;
}

function askClaudeItem(query) {
  return {
    id: 'claude',
    type: 'claude',
    title: `Ask Claude: ${query}`,
    subtitle: 'claude.ai — new chat',
    target: `https://claude.ai/new?q=${encodeURIComponent(query)}`,
  };
}

const MAX_RESULTS = 12;

// "folder: tax" / "site:espn" / "app:chr" / "claude: anything" — first word
// ending in a colon forces a type and bypasses the question heuristics.
const PREFIX_RE = /^(folder|site|website|app|claude):\s*(.*)$/i;
const PREFIX_TYPE = { folder: 'folder', site: 'site', website: 'site', app: 'app' };

function parsePrefix(raw) {
  const m = PREFIX_RE.exec(raw);
  if (!m) return { filter: null, rest: raw };
  const word = m[1].toLowerCase();
  return { filter: word === 'claude' ? 'claude' : PREFIX_TYPE[word], rest: m[2].trim() };
}

function route(rawQuery, items) {
  const raw = String(rawQuery || '').trim();
  if (!raw) return { results: [], enterAction: null };

  const { filter, rest } = parsePrefix(raw);

  if (filter === 'claude') {
    const claude = askClaudeItem(rest || raw);
    return { results: [claude], enterAction: claude };
  }

  if (filter) {
    const pool = items.filter((i) => i.type === filter);
    const ranked = rest
      ? rankItems(rest, pool)
      : [...pool].sort((a, b) => a.title.localeCompare(b.title));
    const results = [...ranked.slice(0, MAX_RESULTS), askClaudeItem(rest || raw)];
    return { results, enterAction: results[0] };
  }

  const ranked = rankItems(stripVerbs(raw), items).slice(0, MAX_RESULTS);
  const hasStrongMatch = ranked.length > 0 && ranked[0].score >= STRONG_MATCH;
  const claude = askClaudeItem(raw);

  const results = isQuestionShaped(raw, hasStrongMatch)
    ? [claude, ...ranked]
    : [...ranked, claude];

  return { results, enterAction: results[0] };
}

module.exports = { STRONG_MATCH, stripVerbs, isQuestionShaped, askClaudeItem, parsePrefix, route };
