const { test } = require('node:test');
const assert = require('node:assert');
const { evaluate, isCalcQuery, calcItem } = require('../src/core/calc.js');

// ---- evaluate ----

test('basic arithmetic', () => {
  assert.strictEqual(evaluate('2+2'), 4);
  assert.strictEqual(evaluate('10-3'), 7);
  assert.strictEqual(evaluate('6*7'), 42);
  assert.strictEqual(evaluate('10/4'), 2.5);
});

test('operator precedence and parentheses', () => {
  assert.strictEqual(evaluate('2+3*4'), 14);
  assert.strictEqual(evaluate('(2+3)*4'), 20);
  assert.strictEqual(evaluate('2^10'), 1024);
  assert.strictEqual(evaluate('2^3^2'), 512); // right-associative
  assert.strictEqual(evaluate('7%3'), 1);
});

test('decimals, unary minus, spaces, commas', () => {
  assert.strictEqual(evaluate('.5+.5'), 1);
  assert.strictEqual(evaluate('-5+10'), 5);
  assert.strictEqual(evaluate('2 * (3 + 4)'), 14);
  assert.strictEqual(evaluate('1,500/3'), 500);
});

test('float noise is cleaned up', () => {
  assert.strictEqual(evaluate('0.1+0.2'), 0.3);
});

test('invalid or incomplete expressions return null', () => {
  assert.strictEqual(evaluate('2+'), null);
  assert.strictEqual(evaluate('abc'), null);
  assert.strictEqual(evaluate(''), null);
  assert.strictEqual(evaluate('(2+3'), null);
  assert.strictEqual(evaluate('2**3'), null);
});

test('non-finite results return null', () => {
  assert.strictEqual(evaluate('1/0'), null);
});

// ---- isCalcQuery ----

test('= prefix is always a calc query', () => {
  assert.strictEqual(isCalcQuery('=2+2'), true);
  assert.strictEqual(isCalcQuery('= anything'), true);
  assert.strictEqual(isCalcQuery('='), true);
});

test('bare math expressions are detected', () => {
  assert.strictEqual(isCalcQuery('2+2'), true);
  assert.strictEqual(isCalcQuery('15*8.5'), true);
  assert.strictEqual(isCalcQuery('(100-20)/4'), true);
});

test('plain text and bare numbers are not calc queries', () => {
  assert.strictEqual(isCalcQuery('chrome'), false);
  assert.strictEqual(isCalcQuery('2048'), false);
  assert.strictEqual(isCalcQuery('192.168.1.1'), false);
  assert.strictEqual(isCalcQuery('open chrome'), false);
});

// ---- calcItem ----

test('calcItem for a valid expression carries the result', () => {
  const it = calcItem('=2+2');
  assert.strictEqual(it.type, 'calc');
  assert.strictEqual(it.title, '= 4');
  assert.strictEqual(it.target, '4');
});

test('calcItem for an incomplete expression has empty target', () => {
  const it = calcItem('=2+');
  assert.strictEqual(it.type, 'calc');
  assert.strictEqual(it.target, '');
});
