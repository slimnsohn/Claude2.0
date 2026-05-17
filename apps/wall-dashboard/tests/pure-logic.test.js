// Run with: node tests/pure-logic.test.js  (from apps/wall-dashboard/)
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

function loadCode(extraGlobals) {
  const code = fs.readFileSync(path.join(__dirname, '../apps-script/Code.gs'), 'utf8');
  const sandbox = Object.assign(
    { module: { exports: {} }, console, JSON, Math, Date },
    extraGlobals || {}
  );
  vm.runInNewContext(code, sandbox);
  return sandbox.module.exports;
}

let pass = 0, fail = 0;
function test(name, fn) {
  try { fn(); pass++; console.log('  PASS ' + name); }
  catch (e) { fail++; console.log('  FAIL ' + name + '\n    ' + e.message); }
}

const lib = loadCode();

// --- routeView_ ---
test('routeView_ defaults to dashboard', () => {
  assert.strictEqual(lib.routeView_(undefined, undefined), 'dashboard');
});
test('routeView_ maps trains', () => {
  assert.strictEqual(lib.routeView_('trains', undefined), 'trains');
});
test('routeView_ maps trains json', () => {
  assert.strictEqual(lib.routeView_('trains', 'json'), 'trainsJson');
});

// === MORE TESTS APPENDED BELOW BY LATER TASKS ===

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
