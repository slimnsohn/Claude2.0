'use strict';

// Safe arithmetic evaluator — recursive descent, no eval().
// Grammar:  expr := term (('+'|'-') term)*
//           term := factor (('*'|'/'|'%') factor)*
//           factor := unary ('^' factor)?          (right-associative)
//           unary := '-' unary | primary
//           primary := NUMBER | '(' expr ')'

function tokenize(input) {
  const cleaned = String(input || '').replace(/[\s,]/g, '');
  const tokens = [];
  let i = 0;
  while (i < cleaned.length) {
    const ch = cleaned[i];
    if ('+-*/%^()'.includes(ch)) {
      tokens.push(ch);
      i++;
    } else if (/[\d.]/.test(ch)) {
      const m = /^\d*\.?\d+/.exec(cleaned.slice(i));
      if (!m) return null;
      tokens.push(Number(m[0]));
      i += m[0].length;
    } else {
      return null;
    }
  }
  return tokens;
}

function evaluate(input) {
  const tokens = tokenize(input);
  if (!tokens || tokens.length === 0) return null;
  let pos = 0;

  const peek = () => tokens[pos];
  const next = () => tokens[pos++];

  function parsePrimary() {
    if (peek() === '(') {
      next();
      const value = parseExpr();
      if (peek() !== ')') throw new Error('unbalanced parens');
      next();
      return value;
    }
    if (typeof peek() === 'number') return next();
    throw new Error('expected number');
  }

  function parseUnary() {
    if (peek() === '-') {
      next();
      return -parseUnary();
    }
    return parsePrimary();
  }

  function parseFactor() {
    const base = parseUnary();
    if (peek() === '^') {
      next();
      return base ** parseFactor();
    }
    return base;
  }

  function parseTerm() {
    let value = parseFactor();
    while (peek() === '*' || peek() === '/' || peek() === '%') {
      const op = next();
      const rhs = parseFactor();
      if (op === '*') value *= rhs;
      else if (op === '/') value /= rhs;
      else value %= rhs;
    }
    return value;
  }

  function parseExpr() {
    let value = parseTerm();
    while (peek() === '+' || peek() === '-') {
      const op = next();
      const rhs = parseTerm();
      value = op === '+' ? value + rhs : value - rhs;
    }
    return value;
  }

  try {
    const result = parseExpr();
    if (pos !== tokens.length || !Number.isFinite(result)) return null;
    return Number(result.toPrecision(12)); // strip float noise (0.1+0.2)
  } catch {
    return null;
  }
}

// "=anything" is always a calc query; bare input counts when it looks like
// math: only digits/operators/parens AND has a digit AND a binary operator.
function isCalcQuery(raw) {
  const q = String(raw || '').trim();
  if (q.startsWith('=')) return true;
  const cleaned = q.replace(/[\s,]/g, '');
  if (!/^[\d.()+\-*/%^]+$/.test(cleaned)) return false;
  if (!/\d/.test(cleaned)) return false;
  // an operator between/after digits (not just "2048" or "192.168.1.1")
  if (!/[+\-*/%^]/.test(cleaned)) return false;
  return evaluate(cleaned) !== null || /[+\-*/%^]$/.test(cleaned);
}

function formatResult(value) {
  return String(value);
}

function calcItem(raw) {
  const expr = String(raw || '').trim().replace(/^=/, '');
  const result = evaluate(expr);
  const valid = result !== null;
  return {
    id: 'calc',
    type: 'calc',
    title: valid ? `= ${formatResult(result)}` : '= …',
    subtitle: valid ? 'Enter to copy to clipboard' : 'keep typing…',
    target: valid ? formatResult(result) : '',
  };
}

module.exports = { evaluate, isCalcQuery, calcItem };
