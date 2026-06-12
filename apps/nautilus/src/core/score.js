'use strict';

// Tiered fuzzy scorer. Tiers are spaced so within-tier bonuses (max +50
// title-length, +30 type priority) can never cross into the next tier.
const TIER = {
  EXACT: 1300,
  WORD_EXACT: 1100, // whole-word match beats title-prefix: "chrome" -> Google Chrome
  PREFIX: 1000,
  WORD_PREFIX: 800,
  SUBSTRING: 600,
  ACRONYM: 450,
  SUBSEQUENCE: 300,
};

const TYPE_BONUS = { app: 30, site: 20, folder: 10, claude: 0 };

function isSubsequence(query, text) {
  let qi = 0;
  for (let ti = 0; ti < text.length && qi < query.length; ti++) {
    if (text[ti] === query[qi]) qi++;
  }
  return qi === query.length;
}

function score(query, title) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return 0;
  const t = String(title || '').toLowerCase();

  let tier = 0;
  const words = t.split(/[\s\-_./]+/).filter(Boolean);
  if (t === q) {
    tier = TIER.EXACT;
  } else if (words.includes(q)) {
    tier = TIER.WORD_EXACT;
  } else if (t.startsWith(q)) {
    tier = TIER.PREFIX;
  } else if (words.some((w) => w.startsWith(q))) {
    tier = TIER.WORD_PREFIX;
  } else if (t.includes(q)) {
    tier = TIER.SUBSTRING;
  } else if (words.map((w) => w[0]).join('').startsWith(q)) {
    tier = TIER.ACRONYM;
  } else if (isSubsequence(q, t)) {
    tier = TIER.SUBSEQUENCE;
  } else {
    return 0;
  }

  const lengthBonus = Math.max(0, 50 - t.length);
  return tier + lengthBonus;
}

function rankItems(query, items) {
  const q = String(query || '').trim();
  if (!q) return [];
  return items
    .map((item) => {
      const base = score(q, item.title);
      if (base === 0) return null;
      return { ...item, score: base + (TYPE_BONUS[item.type] || 0) };
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score);
}

module.exports = { score, rankItems };
