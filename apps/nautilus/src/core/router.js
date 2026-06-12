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

function route(rawQuery, items) {
  const raw = String(rawQuery || '').trim();
  if (!raw) return { results: [], enterAction: null };

  const ranked = rankItems(stripVerbs(raw), items);
  const hasStrongMatch = ranked.length > 0 && ranked[0].score >= STRONG_MATCH;
  const claude = askClaudeItem(raw);

  const results = isQuestionShaped(raw, hasStrongMatch)
    ? [claude, ...ranked]
    : [...ranked, claude];

  return { results, enterAction: results[0] };
}

module.exports = { STRONG_MATCH, stripVerbs, isQuestionShaped, askClaudeItem, route };
